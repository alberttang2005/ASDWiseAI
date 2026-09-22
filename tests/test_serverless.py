"""Stateless deployment regressions. Uses fictional input and a fake provider."""
import base64
import json
import time
import unittest
import uuid
from fastapi.testclient import TestClient
from web.serverless import create_serverless_app, decode_state, encode_state
from test_haven import FakeProvider

KEY = 'test-only-signing-key-with-at-least-32-characters'
ORIGIN = 'https://asdwiseai.org'

class ServerlessTests(unittest.TestCase):
 def setUp(self):
  self.client=TestClient(create_serverless_app(FakeProvider(),KEY,ORIGIN),base_url=ORIGIN)
  self.token=None
 def call(self,path,method='GET',body=None,**extra):
  response=self.client.post('/api/index',headers={'origin':ORIGIN},json={'path':path,'method':method,'body':body or {},'state':self.token,**extra})
  if response.is_success and 'state' in response.json():self.token=response.json()['state']
  return response
 def start(self):
  r=self.call('/sessions','POST',{'name':'Fictional child','age':24,'relationship':'Parent','consent':True})
  self.assertEqual(r.status_code,200,r.text)
  return r.json()['data']
 def mutate(self,s,suffix,body=None,method='POST'):
  r=self.call('/sessions/'+s['id']+suffix,method,{'revision':s['revision'],'request_id':str(uuid.uuid4()),**(body or {})})
  self.assertEqual(r.status_code,200,r.text)
  return r.json()['data']
 def test_new_instance_preserves_progress(self):
  s=self.start();s=self.mutate(s,'/answers/1',{'value':'yes'},'PATCH')
  other=TestClient(create_serverless_app(FakeProvider(),KEY,ORIGIN),base_url=ORIGIN);other.cookies.update(self.client.cookies);self.client=other
  r=self.call('/sessions/'+s['id']);self.assertEqual(r.status_code,200,r.text)
  self.assertEqual(r.json()['data']['current_question']['id'],2)
  self.assertEqual(r.json()['data']['answers']['1']['value'],'yes')
 def test_tamper_owner_expiry_origin_and_no_token(self):
  s=self.start();valid=self.token
  payload,sig=valid.split('.');data=json.loads(base64.urlsafe_b64decode(payload));data['answers']={'1':{'value':'no'}}
  self.token=base64.urlsafe_b64encode(json.dumps(data).encode()).decode()+'.'+sig
  self.assertEqual(self.call('/sessions/'+s['id']).status_code,410)
  self.token=valid;owner=self.client.cookies.get('asdwise_owner');self.client.cookies.clear()
  self.assertEqual(self.call('/sessions/'+s['id']).status_code,410)
  self.client.cookies.set('asdwise_owner',owner)
  data=decode_state(valid,KEY,owner);data['expires_at']=time.time()-1;self.token=encode_state(data,KEY)
  self.assertEqual(self.call('/sessions/'+s['id']).status_code,410)
  self.token=None;self.assertEqual(self.call('/sessions/'+s['id']).status_code,410)
  r=self.client.post('/api/index',headers={'origin':'https://attacker.example'},json={'path':'/health'})
  self.assertEqual(r.status_code,403)
 def test_report_finishes_and_pdf_survives_cold_start(self):
  s=self.start()
  for q in range(1,21):s=self.mutate(s,f'/answers/{q}',{'value':'no' if q in (2,5,12) else 'yes'},'PATCH')
  s=self.mutate(s,'/reports');self.assertEqual(s['report_status'],'ready');self.assertEqual(s['score']['total'],0)
  rid=s['reports'][0]['id']
  other=TestClient(create_serverless_app(FakeProvider(),KEY,ORIGIN),base_url=ORIGIN);other.cookies.update(self.client.cookies);self.client=other
  r=self.call(f"/sessions/{s['id']}/reports/{rid}/pdf")
  self.assertEqual(r.status_code,200,r.text);self.assertTrue(base64.b64decode(r.json()['binary']).startswith(b'%PDF'))
  s=self.mutate(s,'/answers/1',{'value':'no'},'PATCH')
  self.assertEqual(self.call(f"/sessions/{s['id']}/reports/{rid}/pdf").status_code,409)
 def test_audio_and_delete(self):
  s=self.start()
  r=self.call(f"/sessions/{s['id']}/audio/transcriptions",'POST',audio=base64.b64encode(b'a'*100).decode(),content_type='audio/webm')
  self.assertEqual(r.status_code,200,r.text);self.assertIn('transcription',r.json()['data']['text'])
  r=self.call('/sessions/'+s['id'],'DELETE');self.assertEqual(r.status_code,200);self.assertIsNone(self.token)
 def test_get_does_not_extend_expiry(self):
  s=self.start();r=self.call('/sessions/'+s['id']);self.assertEqual(s['expires_at'],r.json()['data']['expires_at'])
 def test_report_failure_returns_retryable_state(self):
  class Failing(FakeProvider):
   async def evaluate(self,*args):raise RuntimeError('fictional failure')
  self.client=TestClient(create_serverless_app(Failing(),KEY,ORIGIN),base_url=ORIGIN)
  s=self.start()
  for q in range(1,21):s=self.mutate(s,f'/answers/{q}',{'value':'unknown'},'PATCH')
  s=self.mutate(s,'/reports');self.assertEqual(s['report_status'],'failed');self.assertEqual(len(s['answers']),20)

if __name__=='__main__':unittest.main()
