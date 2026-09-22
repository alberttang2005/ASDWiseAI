"""Browser-carried, authenticated state; no session database or resident worker.

Every invocation creates an isolated application, restores a signed snapshot,
finishes its work, and returns the next snapshot to the same browser tab.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from .api import create_app
from .providers import Provider
from .security import AIBudget, RequestLimits

MAX_BODY = 4_000_000  # Below Vercel's request/response payload limit.
SESSION_PATH = re.compile(r'^/sessions/([0-9a-f-]{36})(?:/(?:turns|control|context|answers/[0-9]+|reports(?:/[0-9a-f-]{36}(?:/pdf)?)?|audio/(?:transcriptions|speech)))?$')


def encode_state(state, key):
    raw = json.dumps(state, separators=(',', ':'), ensure_ascii=False).encode()
    payload = base64.urlsafe_b64encode(raw).decode()
    signature = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + '.' + signature


def decode_state(token, key, owner):
    try:
        if not isinstance(token, str):
            raise ValueError()
        payload, signature = token.rsplit('.', 1)
        expected = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        state = json.loads(base64.b64decode(payload, altchars=b'-_', validate=True))
        if state['owner'] != owner or state['expires_at'] <= time.time():
            raise ValueError()
        return state
    except (ValueError, KeyError, TypeError):
        raise HTTPException(410, 'This temporary session expired or could not be verified. Start a new conversation.') from None


def create_serverless_app(provider=None, signing_key=None, public_origin=None):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    # These are per-instance safeguards, not distributed billing/rate limits.
    limits, budget = RequestLimits(), AIBudget()
    provider = provider or Provider()

    @app.middleware('http')
    async def no_cache(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/ready')
    async def ready(request: Request):
        secret = os.getenv('ASDWISE_GATEWAY_SECRET', '')
        if not secret or not secrets.compare_digest(request.headers.get('x-gateway-secret', ''), secret):
            raise HTTPException(403, 'Forbidden')
        return {'ready': True}

    @app.post('/api/index')
    async def dispatch(request: Request):
        origin = public_origin or os.getenv('ASDWISE_PUBLIC_ORIGIN')
        if not origin:
            raise HTTPException(503, 'The service origin is not configured.')
        if request.headers.get('origin') != origin:
            raise HTTPException(403, 'Request origin was not accepted.')
        key = signing_key or os.getenv('ASDWISE_SESSION_SECRET', '')
        if len(key) < 32:
            raise HTTPException(503, 'The service signing secret is not configured.')
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BODY:
                raise HTTPException(413, 'Request too large. Use a shorter recording or start a new interview.')
        try:
            envelope = json.loads(raw)
            if not isinstance(envelope, dict):
                raise ValueError()
            path, method = envelope['path'], envelope.get('method', 'GET')
            if not isinstance(path, str) or not isinstance(method, str):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise HTTPException(400, 'Invalid request.') from None
        match = SESSION_PATH.fullmatch(path)
        if path not in ('/health', '/sessions') and not match:
            raise HTTPException(404, 'Unknown operation.')
        if method not in ('GET', 'POST', 'PATCH', 'DELETE'):
            raise HTTPException(405, 'Unsupported method.')
        owner = request.cookies.get('asdwise_owner')
        try:
            uuid.UUID(owner or '')
        except ValueError:
            owner = str(uuid.uuid4())
        internal_secret = secrets.token_hex(32)
        inner = create_app(provider=provider, gateway_secret=internal_secret,
                           request_limits=limits, ai_budget=budget)
        store = inner.state.store
        if match:
            state = decode_state(envelope.get('state', ''), key, owner)
            if state['id'] != match[1]:
                raise HTTPException(404, 'Session not found.')
            # Do not renew expiry on reads; only existing mutation handlers do so.
            store.sessions[state['id']] = (time.monotonic(), state)
        headers = {'x-owner': owner, 'x-gateway-secret': internal_secret}
        kwargs = {}
        if 'audio' in envelope:
            try:
                kwargs['content'] = base64.b64decode(envelope['audio'], validate=True)
            except (ValueError, TypeError):
                raise HTTPException(422, 'Invalid recording.') from None
            headers['content-type'] = envelope.get('content_type', '')
        elif method != 'GET':
            kwargs['json'] = envelope.get('body', {})
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=inner), base_url='http://internal') as client:
                result = await client.request(method, path, headers=headers, **kwargs)
                # Never leave a report running after a function response returns.
                if inner.state.jobs:
                    await asyncio.gather(*tuple(inner.state.jobs))
                if result.is_success and method == 'POST' and path.endswith('/reports'):
                    result = await client.get(path.rsplit('/', 1)[0], headers=headers)
                if result.headers.get('content-type', '').startswith('application/json'):
                    data = result.json()
                    reply = {'data': data}
                else:
                    reply = {'binary': base64.b64encode(result.content).decode(),
                             'content_type': result.headers.get('content-type', 'application/octet-stream')}
                if result.is_success:
                    states = store.list(owner)
                    reply['state'] = encode_state(states[0], key) if states else None
                response = JSONResponse(reply, status_code=result.status_code)
                if len(response.body) > MAX_BODY:
                    raise HTTPException(413, 'Interview or reports are too large. Download your current report before continuing.')
                response.set_cookie('asdwise_owner', owner, httponly=True, secure=origin.startswith('https:'), samesite='strict', path='/')
                return response
        finally:
            for task in tuple(inner.state.jobs):
                task.cancel()
            if inner.state.jobs:
                await asyncio.gather(*tuple(inner.state.jobs), return_exceptions=True)
            store.clear()
    return app
