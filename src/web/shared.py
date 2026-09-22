"""Encrypted TTL sessions and atomic admission controls shared by Vercel instances."""
import asyncio
import hashlib
import inspect
import json
import os
import time
import uuid
import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException
from .store import SessionTooLarge


class AsyncFacade:
    """Keep the local synchronous store/test interface, with async cloud I/O."""
    def __init__(self, target):
        self.target = target

    def __getattr__(self, name):
        async def call(*args, **kwargs):
            result = getattr(self.target, name)(*args, **kwargs)
            return await result if inspect.isawaitable(result) else result
        return call


class Redis:
    def __init__(self):
        self.url = os.environ['UPSTASH_REDIS_REST_URL'].rstrip('/')
        if not self.url.startswith('https://'):
            raise ValueError('Redis REST requires HTTPS')
        self.token = os.environ['UPSTASH_REDIS_REST_TOKEN']
        namespace = os.environ['ASDWISE_REDIS_NAMESPACE']
        self.prefix = 'asdwise:{' + hashlib.sha256(namespace.encode()).hexdigest()[:24] + '}:'

    async def command(self, *args):
        # No automatic retries: a timed-out mutation may already have committed.
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(self.url, headers={'Authorization': 'Bearer '+self.token}, json=list(args))
                response.raise_for_status()
                result = response.json()
            if 'error' in result:
                raise ValueError('Redis command failed')
            return result['result']
        except (httpx.HTTPError, ValueError, KeyError):
            raise HTTPException(503, 'Temporary session storage is unavailable. Please retry.') from None

    async def eval(self, script, keys, args=()):
        return await self.command('EVAL', script, len(keys), *keys, *args)


PUT = '''
local now=tonumber(redis.call('TIME')[1])
local version=redis.call('HGET',KEYS[1],'version')
if ARGV[1]=='new' then
 if version then return -1 end
 redis.call('ZREMRANGEBYSCORE',KEYS[2],'-inf',now)
 redis.call('ZREMRANGEBYSCORE',KEYS[3],'-inf',now)
 if redis.call('ZCARD',KEYS[2])>=100 or redis.call('ZCARD',KEYS[3])>=20 then return -2 end
else
 if not version or version~=ARGV[1] then return -1 end
end
local next=version and tonumber(version)+1 or 1
redis.call('HSET',KEYS[1],'version',next,'payload',ARGV[2],'owner',ARGV[3])
redis.call('EXPIRE',KEYS[1],ARGV[4])
redis.call('ZADD',KEYS[2],now+tonumber(ARGV[4]),ARGV[5])
redis.call('ZADD',KEYS[3],now+tonumber(ARGV[4]),ARGV[5])
redis.call('EXPIRE',KEYS[2],ARGV[4])
redis.call('EXPIRE',KEYS[3],ARGV[4])
return next
'''
DELETE = '''
if redis.call('HGET',KEYS[1],'owner')~=ARGV[1] then return 0 end
redis.call('DEL',KEYS[1])
redis.call('ZREM',KEYS[2],ARGV[2])
redis.call('ZREM',KEYS[3],ARGV[2])
return 1
'''


class RedisStore:
    def __init__(self, redis, key=None, ttl_seconds=1800):
        self.redis, self.ttl_seconds = redis, ttl_seconds
        self.cipher = Fernet(key or os.environ['ASDWISE_SESSION_KEY'].encode())

    def keys(self, sid, owner):
        owner_hash = hashlib.sha256(owner.encode()).hexdigest()
        return [self.redis.prefix+'session:'+sid, self.redis.prefix+'sessions', self.redis.prefix+'owner:'+owner_hash], owner_hash

    async def put(self, s):
        s['expires_at'] = time.time()+self.ttl_seconds
        raw = json.dumps({k:v for k,v in s.items() if k!='_storage_version'}, ensure_ascii=False).encode()
        if len(s.get('turns', []))>300 or len(raw)>2*1024*1024:
            raise SessionTooLarge('Session limit reached. Download your report or start a new session.')
        keys, owner = self.keys(s['id'], s['owner'])
        version = await self.redis.eval(PUT, keys, [str(s.get('_storage_version', 'new')), self.cipher.encrypt(raw).decode(), owner, self.ttl_seconds, s['id']])
        if version == -1:
            raise HTTPException(409, 'Session changed or expired. Refresh and review before retrying.')
        if version == -2:
            raise HTTPException(429, 'Session capacity reached. Please retry later.')
        s['_storage_version'] = version

    async def get(self, sid, owner):
        keys, owner_hash = self.keys(sid, owner)
        result = await self.redis.command('HMGET', keys[0], 'payload', 'version', 'owner')
        if not result or not result[0] or result[2]!=owner_hash:
            return None
        s = json.loads(self.cipher.decrypt(result[0].encode()))
        if s['owner']!=owner or s['id']!=sid or s['expires_at']<=time.time():
            return None
        s['_storage_version'] = int(result[1])
        return s

    async def delete(self, sid, owner):
        keys, owner_hash = self.keys(sid, owner)
        await self.redis.eval(DELETE, keys, [owner_hash, sid])

    async def count(self, owner=None):
        key = self.redis.prefix+'sessions' if owner is None else self.keys('',owner)[0][2]
        return await self.redis.eval("local now=tonumber(redis.call('TIME')[1]); redis.call('ZREMRANGEBYSCORE',KEYS[1],'-inf',now); return redis.call('ZCARD',KEYS[1])", [key])

    async def expire(self):
        pass  # Redis expires encrypted session keys even with no running function.


LIMIT = '''
for i=1,#KEYS do
 if tonumber(redis.call('GET',KEYS[i]) or '0')>=tonumber(ARGV[i]) then return 0 end
end
for i=1,#KEYS do
 local n=redis.call('INCR',KEYS[i]); if n==1 then redis.call('EXPIRE',KEYS[i],60) end
end
return 1
'''


class RedisLimits:
    def __init__(self, redis):
        self.redis=redis

    async def allow(self, owner, creating=False):
        keys=[self.redis.prefix+'rate:global',self.redis.prefix+'rate:'+hashlib.sha256(owner.encode()).hexdigest()]
        caps=[600,120]
        if creating:
            keys.append(self.redis.prefix+'rate:creation');caps.append(20)
        return bool(await self.redis.eval(LIMIT,keys,caps))

    async def expire(self):
        pass


UNLOCK = "if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('DEL',KEYS[1]) end; return 0"


class RedisLock:
    def __init__(self, redis, sid):
        self.redis=redis
        # A fixed number of shared stripes also bounds bogus-ID lock keys.
        stripe=int(hashlib.sha256(sid.encode()).hexdigest(),16)%256
        self.key=redis.prefix+'lock:'+str(stripe)
        self.token=str(uuid.uuid4())

    async def __aenter__(self):
        if not await self.redis.command('SET',self.key,self.token,'NX','EX',90):
            raise HTTPException(429,'This session is busy. Please retry shortly.',headers={'Retry-After':'2'})
        return self

    async def __aexit__(self,*exc):
        await self.redis.eval(UNLOCK,[self.key],[self.token])


class RedisLocks:
    def __init__(self,redis):self.redis=redis
    def __getitem__(self,sid):return RedisLock(self.redis,sid)


RESERVE = '''
local now=tonumber(redis.call('TIME')[1])
redis.call('ZREMRANGEBYSCORE',KEYS[1],'-inf',now)
if redis.call('ZCARD',KEYS[1])>=tonumber(ARGV[1]) then return -1 end
local spent=tonumber(redis.call('GET',KEYS[2]) or '0')
if spent+tonumber(ARGV[2])>tonumber(ARGV[3]) then return -2 end
redis.call('INCRBY',KEYS[2],ARGV[2])
redis.call('ZADD',KEYS[1],now+180,ARGV[4])
redis.call('EXPIRE',KEYS[1],180)
return 1
'''


class RedisBudget:
    def __init__(self,redis,concurrency=None,units=None):
        self.redis=redis
        self.concurrency=int(os.getenv('ASDWISE_AI_CONCURRENCY','4')) if concurrency is None else concurrency
        self.units=int(os.getenv('ASDWISE_AI_BUDGET_UNITS','1000')) if units is None else units
        if self.concurrency<1 or self.units<0:raise ValueError('Invalid AI allowance')

    async def reserve(self,units):
        token=str(uuid.uuid4())
        result=await self.redis.eval(RESERVE,[self.redis.prefix+'ai:active',self.redis.prefix+'ai:spent'],[self.concurrency,units,self.units,token])
        if result==-1:raise HTTPException(429,'The service is busy. Please retry shortly.',headers={'Retry-After':'30'})
        if result==-2:raise HTTPException(503,'The service usage allowance has been reached. Please contact the operator.')
        return token

    async def release(self,token):
        await self.redis.command('ZREM',self.redis.prefix+'ai:active',token)

    async def call(self,units,operation,*args):
        token=await self.reserve(units)
        try:return await asyncio.wait_for(operation(*args),timeout=125)
        finally:await self.release(token)
