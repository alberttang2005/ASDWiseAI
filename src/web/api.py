"""Local-pilot API. Run one worker behind the authenticated Next.js gateway."""
import asyncio, copy, hashlib, json, os, secrets, time, uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from .domain import SessionInput, Mutation, TurnInput, AnswerInput, ControlInput, ContextInput, QUESTIONS, ROOT, score
from .store import Store
from .providers import Provider
from openai import APITimeoutError
from . import reports

def now():return datetime.now(timezone.utc).isoformat()
def uid():return str(uuid.uuid4())

def create_app(data_dir=None, provider=None, gateway_secret=None, report_timeout=120):
 store=Store()
 store.expire();store.recover()
 provider=provider or Provider()
 secret=gateway_secret or os.getenv('ASDWISE_GATEWAY_SECRET')
 if not secret:raise RuntimeError('Start with the launcher; a private gateway secret is required.')
 @asynccontextmanager
 async def lifespan(app):
  async def cleanup():
   while True:
    await asyncio.sleep(30)
    store.expire()
  cleanup_task=asyncio.create_task(cleanup())
  try:yield
  finally:
   cleanup_task.cancel()
   for task in jobs:task.cancel()
   with suppress(asyncio.CancelledError):await cleanup_task
   if jobs:await asyncio.gather(*jobs,return_exceptions=True)
   store.clear()
 app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
 locks=defaultdict(asyncio.Lock);limits=defaultdict(deque);jobs=set()
 app.state.store=store
 app.state.report_timeout=report_timeout
 @app.middleware('http')
 async def guard(request,call_next):
  if not secrets.compare_digest(request.headers.get('x-gateway-secret',''),secret):return Response(status_code=403)
  owner=request.headers.get('x-owner','')
  try:uuid.UUID(owner)
  except ValueError:return Response(status_code=403)
  request.state.owner=owner
  q=limits[owner];current=time.monotonic()
  while q and q[0]<current-60:q.popleft()
  if len(q)>120:return Response('Too many requests. Please wait a minute.',status_code=429)
  q.append(current)
  if int(request.headers.get('content-length','0') or 0)>8*1024*1024:return Response(status_code=413)
  result=await call_next(request);result.headers['Cache-Control']='no-store';return result
 def get(sid,request):
  s=store.get(sid,request.state.owner)
  if not s or s.get('mode')!='interactive':raise HTTPException(404,'Session not found')
  return s
 def public(s):
  return {k:v for k,v in s.items() if k not in ('owner','requests','reports') } | {'score':score(s['answers']),'reports':[{'id':r['id'],'created':r['created'],'revision':r['revision'],'stale':r['revision']!=s['revision']} for r in s['reports']]}
 def check(s,m):
  if m.request_id in s['requests']:return False
  if m.revision!=s['revision']:raise HTTPException(409,'Session changed. Refresh and review before retrying.')
  return True
 def save(s,m):
  s['revision']+=1;s['requests']=(s['requests']+[m.request_id])[-200:];store.put(s);return public(s)
 def turn(s,role,text,qid=None,**extra):
  t={'id':uid(),'role':role,'text':text,'question_id':qid,'created':now(),**extra};s['turns'].append(t);return t
 def ask(s):
  q=QUESTIONS[s['index']];s['current_question']=q
  turn(s,'guide',q['text'],q['id'])
 def active(s):
  if s['status']!='running':raise HTTPException(409,'Resume the interview before responding.')
 @app.get('/health')
 async def health():return {'live_available':provider.enabled,'audio_available':provider.enabled,'storage':'temporary memory only; expires after 30 minutes without updates','reference_available':reports.REFERENCE_PATH.exists()}
 @app.post('/sessions')
 async def create(body:SessionInput,request:Request):
  if not body.consent:raise HTTPException(422,'Please review and accept the data notice.')
  if body.mode=='interactive' and not provider.enabled:raise HTTPException(503,'Conversations are temporarily unavailable. Please try again later.')
  store.expire()
  if len(store.sessions)>=100:raise HTTPException(503,'The service is busy. Please try again shortly.')
  if len(store.list(request.state.owner))>=20:raise HTTPException(409,'Delete an old session before creating another.')
  child={'name':body.name.strip(),'age':body.age,'relationship':body.relationship.strip()}
  if not child['name'] or not child['relationship']:raise HTTPException(422,'Enter a name and caregiver relationship.')
  s={'id':uid(),'owner':request.state.owner,'child':child,'mode':body.mode,'observation_context':body.observation_context.model_dump(),'consent':{'version':'2026-09-16','accepted_at':now()},'created':now(),'revision':0,'status':'running','index':0,'answers':{},'turns':[],'pending':None,'context':{'onset':'','impact':'','routines':'','interests':'','other_observations':''},'requests':[],'reports':[],'report_status':'idle','report_error':None}
  turn(s,'guide','Welcome. I’m the ASDWise AI screening guide. We’ll review one question at a time. You can pause whenever you need.');ask(s);store.put(s);return public(s)
 @app.get('/sessions/{sid}')
 async def read(sid:str,request:Request):return public(get(sid,request))
 @app.delete('/sessions/{sid}')
 async def delete(sid:str,request:Request):
  async with locks[sid]:get(sid,request);store.delete(sid,request.state.owner)
  return {'deleted':True}
 @app.post('/sessions/{sid}/turns')
 async def submit(sid:str,body:TurnInput,request:Request):
  async with locks[sid]:
   s=get(sid,request)
   if not check(s,body):return public(s)
   active(s)
   if len(s['turns'])>180:raise HTTPException(422,'Conversation limit reached. Review your responses.')
   if not body.text.strip():raise HTTPException(422,'Enter a response.')
   try:reply=await provider.guide(s,body.text)
   except Exception:raise HTTPException(502,'The guide could not respond. Your answer has not advanced; please retry.')
   t=turn(s,'caregiver',body.text.strip(),s['current_question']['id'],modality=body.modality,original_transcript=body.original_transcript)
   turn(s,'guide',reply['response'],s['current_question']['id'])
   s['pending']={'turn_id':t['id'],'suggested':reply['suggested_answer']}
   return save(s,body)
 @app.patch('/sessions/{sid}/answers/{qid}')
 async def confirm(sid:str,qid:int,body:AnswerInput,request:Request):
  async with locks[sid]:
   s=get(sid,request)
   if not check(s,body):return public(s)
   if not 1<=qid<=20:raise HTTPException(422,'Invalid question')
   if s['status'] in ('paused','stopped'):raise HTTPException(409,'Resume before editing responses.')
   existing=s['answers'].get(str(qid));current=qid==s['current_question']['id'] and s['status']=='running'
   if not existing and not current:raise HTTPException(409,'Answer the current question first.')
   evidence=s['pending']['turn_id'] if current and s['pending'] else existing['turn_id'] if existing else None
   if not evidence:evidence=turn(s,'caregiver',body.value,qid,modality='selection')['id']
   s['answers'][str(qid)]={'value':body.value,'turn_id':evidence,'confirmed':True}
   if current:
    s['pending']=None
    if qid==20:s['status']='complete';turn(s,'guide','Thank you. Review your responses and any uncertain items before generating your report.')
    else:s['index']+=1;ask(s)
   return save(s,body)
 @app.post('/sessions/{sid}/control')
 async def control(sid:str,body:ControlInput,request:Request):
  async with locks[sid]:
   s=get(sid,request)
   if not check(s,body):return public(s)
   if body.action=='keepalive':
    s['requests']=(s['requests']+[body.request_id])[-200:];store.put(s);return public(s)
   if body.action in ('pause','stop'):
    if s['status']=='running':s['status']='paused' if body.action=='pause' else 'stopped'
   elif body.action=='resume':
    if s['status'] in ('paused','stopped'):s['status']='running'
   elif body.action=='reset':
    s.update(index=0,status='running',answers={},turns=[],pending=None,context={'onset':'','impact':'','routines':'','interests':'','other_observations':''});ask(s)
   return save(s,body)
 @app.patch('/sessions/{sid}/context')
 async def context(sid:str,body:ContextInput,request:Request):
  async with locks[sid]:
   s=get(sid,request)
   if not check(s,body):return public(s)
   s['context']={k:getattr(body,k) for k in ['onset','impact','routines','interests','other_observations']}
   # Keep old context in audit history, mark superseded so reports cannot cite it as current.
   for t in s['turns']:
    if t.get('context_key'):t['role']='superseded'
   for k,v in s['context'].items():
    if v.strip():turn(s,'caregiver',v.strip(),context_key=k,modality='text')
   return save(s,body)
 async def generate(snapshot,owner,rid):
  try:
   ref=reports.reference()
   analysis=await asyncio.wait_for(provider.evaluate(snapshot,ref),timeout=app.state.report_timeout)
   analysis=reports.validate_analysis(analysis,snapshot,ref)
   report=reports.assemble(snapshot,analysis,ref,provider.evaluator_model)
   report.update(id=rid,created=now())
   async with locks[snapshot['id']]:
    current=store.get(snapshot['id'],owner)
    if current:
     current['reports'].append(report);current['reports']=current['reports'][-10:];current['report_status']='ready';current['report_error']=None;store.put(current)
  except Exception as error:
   timed_out=isinstance(error,(asyncio.TimeoutError,APITimeoutError))
   async with locks[snapshot['id']]:
    current=store.get(snapshot['id'],owner)
    if current:
     current['report_status']='failed';current['report_error_code']='timeout' if timed_out else 'validation_or_provider'
     current['report_error']='The report took too long. Your answers are still here. Retry when you are ready.' if timed_out else 'We could not verify this report. Your answers are still here. Please retry.'
     store.put(current)
 @app.post('/sessions/{sid}/reports')
 async def generate_report(sid:str,body:Mutation,request:Request):
  async with locks[sid]:
   s=get(sid,request)
   if not check(s,body):return public(s)
   if s['status']!='complete':raise HTTPException(409,'Finish the interview before generating a report.')
   if s['report_status']=='generating':return public(s)
   s['report_status']='generating';s['report_error']=None;s['report_error_code']=None;s['report_started_at']=time.time();s['report_deadline_at']=time.time()+report_timeout;s['requests'].append(body.request_id);store.put(s)
   task=asyncio.create_task(generate(copy.deepcopy(s),s['owner'],uid()));jobs.add(task);task.add_done_callback(jobs.discard)
   return public(s)
 @app.get('/sessions/{sid}/reports/{rid}')
 async def report_json(sid:str,rid:str,request:Request):
  s=get(sid,request);r=next((r for r in s['reports'] if r['id']==rid),None)
  if not r:raise HTTPException(404,'Report not found')
  return r|{'stale':r['revision']!=s['revision']}
 @app.get('/sessions/{sid}/reports/{rid}/pdf')
 async def report_pdf(sid:str,rid:str,request:Request):
  r=await report_json(sid,rid,request)
  if r['stale']:raise HTTPException(409,'Responses changed. Regenerate before downloading.')
  return Response(reports.pdf(r),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="ASDWise-screening-report.pdf"'})
 @app.get('/sessions/{sid}/events')
 async def events(sid:str,request:Request):
  get(sid,request)
  async def stream():
   previous=None
   for _ in range(180):
    if await request.is_disconnected():break
    s=store.get(sid,request.state.owner)
    if not s:break
    token=(s['revision'],s['report_status'],s.get('expires_at'))
    if token!=previous:yield 'data: '+json.dumps(public(s))+'\n\n';previous=token
    else:yield ': heartbeat\n\n'
    await asyncio.sleep(1)
  return StreamingResponse(stream(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})
 @app.post('/sessions/{sid}/audio/transcriptions')
 async def transcribe(sid:str,request:Request):
  s=get(sid,request);active(s)
  if not provider.enabled:raise HTTPException(503,'Audio requires the server API key.')
  mime=request.headers.get('content-type','').split(';')[0]
  if mime not in ('audio/webm','audio/mp4','audio/ogg','audio/wav'):raise HTTPException(415,'Unsupported audio format. Please type your answer.')
  chunks=[];size=0
  async for chunk in request.stream():
   size+=len(chunk)
   if size>8*1024*1024:raise HTTPException(413,'Recording too large. Use a shorter recording.')
   chunks.append(chunk)
  if size<100:raise HTTPException(422,'No audio captured.')
  try:text=await provider.transcribe(b''.join(chunks),mime)
  except Exception:raise HTTPException(502,'Transcription failed. Please retry or type.')
  if not text.strip():raise HTTPException(422,'No speech detected. Please try again.')
  return {'text':text[:6000]}
 @app.post('/sessions/{sid}/audio/speech')
 async def speech(sid:str,request:Request):
  s=get(sid,request)
  if s['status']!='running':raise HTTPException(409,'Speech is available while the interview is running.')
  if not provider.enabled:raise HTTPException(503,'Audio requires the server API key.')
  body=await request.json();t=next((t for t in s['turns'] if t['id']==body.get('turn_id') and t['role']=='guide'),None)
  if not t:raise HTTPException(422,'Guide message not found')
  try:audio=await provider.speech(t['text'])
  except Exception:raise HTTPException(502,'Speech playback unavailable. The text is still available.')
  return Response(audio,media_type='audio/mpeg')
 return app
