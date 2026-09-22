"""Security regressions using synthetic input and no external AI calls."""
import asyncio
import copy
import time
import unittest
import uuid
from fastapi import HTTPException
from fastapi.testclient import TestClient
from web.api import create_app
from web.security import AIBudget, RequestLimits
from web.store import SessionTooLarge
from test_haven import FakeProvider


class AdmissionTests(unittest.TestCase):
 def test_identity_rotation_does_not_reset_global_limit(self):
  clock=[0]
  limits=RequestLimits(clock=lambda:clock[0],global_limit=5)
  for _ in range(5):self.assertTrue(limits.allow(str(uuid.uuid4())))
  self.assertFalse(limits.allow(str(uuid.uuid4())))
  clock[0]=61;limits.expire()
  self.assertEqual(limits.owners,{})
  self.assertTrue(limits.allow('new'))

 def test_owner_table_fails_closed_at_capacity(self):
  limits=RequestLimits(max_owners=2)
  self.assertTrue(limits.allow('a'));self.assertTrue(limits.allow('b'))
  self.assertFalse(limits.allow('c'));self.assertEqual(len(limits.owners),2)

 def test_global_creation_limit_survives_cookie_rotation(self):
  limits=RequestLimits()
  for _ in range(20):self.assertTrue(limits.allow(str(uuid.uuid4()),creating=True))
  self.assertFalse(limits.allow('new',creating=True))
  self.assertTrue(limits.allow('existing'))


class BudgetTests(unittest.IsolatedAsyncioTestCase):
 async def test_concurrency_failure_and_exhaustion(self):
  budget=AIBudget(concurrency=1,units=2)
  budget.reserve(1)
  with self.assertRaises(HTTPException) as error:budget.reserve(1)
  self.assertEqual(error.exception.status_code,429)
  self.assertEqual(budget.remaining,1)
  budget.release()
  async def fail():raise RuntimeError('synthetic failure')
  with self.assertRaises(RuntimeError):await budget.call(1,fail)
  self.assertEqual(budget.active,0)
  with self.assertRaises(HTTPException) as error:budget.reserve(1)
  self.assertEqual(error.exception.status_code,503)

 async def test_cancellation_releases_capacity_without_refunding_usage(self):
  budget=AIBudget(concurrency=1,units=2)
  started=asyncio.Event()
  async def wait():started.set();await asyncio.Event().wait()
  task=asyncio.create_task(budget.call(1,wait))
  await started.wait();task.cancel()
  with self.assertRaises(asyncio.CancelledError):await task
  self.assertEqual((budget.active,budget.remaining),(0,1))


class SecurityAPITests(unittest.TestCase):
 def setUp(self):
  self.app=create_app(provider=FakeProvider(),gateway_secret='test-secret')
  self.client=TestClient(self.app);self.client.__enter__()
  self.headers={'x-gateway-secret':'test-secret','x-owner':str(uuid.uuid4())}
 def tearDown(self):self.client.__exit__(None,None,None)
 def create(self):
  response=self.client.post('/sessions',headers=self.headers,json={'name':'Synthetic','age':24,'relationship':'Parent','consent':True})
  self.assertEqual(response.status_code,200,response.text);return response.json()
 def mutate(self,s,path,body,method='POST'):
  return self.client.request(method,'/sessions/'+s['id']+path,headers=self.headers,json={'revision':s['revision'],'request_id':str(uuid.uuid4()),**body})

 def test_context_history_bounded_and_latest_evidence_preserved(self):
  s=self.create()
  for i in range(60):
   body={key:str(i)+'x'*1900 for key in ['onset','impact','routines','interests','other_observations']}
   response=self.mutate(s,'/context',body,'PATCH')
   self.assertEqual(response.status_code,200,response.text);s=response.json()
  context=[t for t in s['turns'] if t.get('context_key')]
  self.assertEqual(len(context),55)
  self.assertEqual(len([t for t in context if t['role']=='caregiver']),5)
  self.assertTrue(all(t['text'].startswith('59') for t in context if t['role']=='caregiver'))
  self.assertEqual(s['turns'][0]['role'],'guide')

 def test_nonexistent_session_requests_do_not_allocate_locks(self):
  initial=tuple(self.app.state.locks.locks)
  for _ in range(80):
   r=self.client.delete('/sessions/'+str(uuid.uuid4()),headers=self.headers)
   self.assertEqual(r.status_code,404)
  self.assertEqual(tuple(self.app.state.locks.locks),initial)

 def test_rotated_identity_still_hits_global_http_limit(self):
  self.app.state.limits.global_limit=3
  for _ in range(3):
   self.assertEqual(self.client.get('/health',headers={**self.headers,'x-owner':str(uuid.uuid4())}).status_code,200)
  response=self.client.get('/health',headers={**self.headers,'x-owner':str(uuid.uuid4())})
  self.assertEqual(response.status_code,429);self.assertEqual(response.headers['retry-after'],'60')

 def test_readiness_requires_secret_and_survives_exhausted_quotas(self):
  self.app.state.limits.global_limit=0;self.app.state.ai_budget.remaining=0
  self.assertEqual(self.client.get('/ready').status_code,403)
  response=self.client.get('/ready',headers={'x-gateway-secret':'test-secret'})
  self.assertEqual(response.status_code,200)
  self.assertEqual(len(self.app.state.limits.owners),0)

 def test_ai_exhaustion_leaves_session_unchanged(self):
  s=self.create();self.app.state.ai_budget.remaining=0
  for path,body in [('/turns',{'text':'Synthetic observation'}),('/audio/speech',{'turn_id':s['turns'][0]['id']})]:
   response=self.mutate(s,path,body)
   self.assertEqual(response.status_code,503,response.text)
  response=self.client.post('/sessions/'+s['id']+'/audio/transcriptions',headers={**self.headers,'content-type':'audio/webm'},content=b'x'*500)
  self.assertEqual(response.status_code,503)
  self.assertEqual(self.app.state.store.get(s['id'],self.headers['x-owner'])['revision'],0)

 def test_report_rejected_before_background_job_when_capacity_full(self):
  s=self.create()
  for qid in range(1,21):
   r=self.mutate(s,f'/answers/{qid}',{'value':'unknown'},'PATCH')
   self.assertEqual(r.status_code,200,r.text);s=r.json()
  self.app.state.ai_budget.active=self.app.state.ai_budget.concurrency
  response=self.mutate(s,'/reports',{})
  self.assertEqual(response.status_code,429,response.text)
  self.assertEqual(self.app.state.store.get(s['id'],self.headers['x-owner'])['report_status'],'idle')
  self.app.state.ai_budget.active=0
  stored=self.app.state.store.get(s['id'],self.headers['x-owner'])
  stored['requests']=[str(uuid.uuid4()) for _ in range(200)]
  self.app.state.store.put(stored)
  remaining=self.app.state.ai_budget.remaining
  response=self.mutate(s,'/reports',{})
  self.assertEqual(response.status_code,200,response.text)
  for _ in range(100):
   stored=self.app.state.store.get(s['id'],self.headers['x-owner'])
   if stored['report_status']!='generating' and self.app.state.ai_budget.active==0:break
   time.sleep(.01)
  self.assertEqual(stored['report_status'],'ready')
  self.assertEqual(len(stored['requests']),200)
  self.assertEqual((self.app.state.ai_budget.active,self.app.state.ai_budget.remaining),(0,remaining-20))

 def test_store_rejects_oversize_atomically(self):
  s=self.create();original=copy.deepcopy(s)
  stored=self.app.state.store.get(s['id'],self.headers['x-owner'])
  stored['context']['onset']='x'*(2*1024*1024)
  with self.assertRaises(SessionTooLarge):self.app.state.store.put(stored)
  self.assertEqual(self.app.state.store.get(s['id'],self.headers['x-owner'])['context'],original['context'])
  stored['context']=original['context'];stored['turns']=[{}]*301
  with self.assertRaises(SessionTooLarge):self.app.state.store.put(stored)
