"""Behavioral regression tests: no live provider calls or patient data."""
import copy, json, tempfile, time, unittest, uuid
from pathlib import Path
from fastapi.testclient import TestClient
from web.api import create_app
from web.domain import QUESTIONS, SCORER, score
from web import reports

class FakeProvider:
 enabled=True
 evaluator_model='test-provider'
 fail=False
 async def guide(self,s,text):
  if self.fail:raise RuntimeError('provider unavailable')
  return {'response':'Could you tell me what happens most often?','suggested_answer':'unknown'}
 async def evaluate(self,s,ref):return reports.demo_analysis(s,ref)
 async def transcribe(self,b,m):return 'A synthetic transcription to review.'
 async def speech(self,t):return b'ID3-test-only'

class ScoringTests(unittest.TestCase):
 def test_boundaries_and_reverse_scoring(self):
  safe={q['id']:'no' if q['id'] in (2,5,12) else 'yes' for q in QUESTIONS}
  for count,band in [(0,'LOW'),(2,'LOW'),(3,'MODERATE'),(7,'MODERATE'),(8,'HIGH'),(20,'HIGH')]:
   answers=safe.copy()
   for i in range(1,count+1):answers[i]='yes' if safe[i]=='no' else 'no'
   result=SCORER.score_responses(answers)
   self.assertEqual((result['total_score'],result['risk_level']),(count,band))
 def test_missing_unknown_never_low(self):
  for a in [{},{1:'unknown'},{1:'yesterday'},{i:'yes' for i in range(1,20)}]:
   r=SCORER.score_responses(a);self.assertEqual(r['risk_level'],'INCOMPLETE');self.assertIsNone(r['total_score'])
 def test_invalid_input(self):
  with self.assertRaises(ValueError):SCORER.score_responses({21:'yes'})
  with self.assertRaises(ValueError):SCORER.is_at_risk(1,'not sure')

class APITests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='haven-test-',dir='/private/tmp');self.provider=FakeProvider()
  self.app=create_app(self.tmp.name,self.provider,'test-secret')
  self.client=TestClient(self.app);self.client.__enter__()
  self.headers={'x-gateway-secret':'test-secret','x-owner':str(uuid.uuid4())}
 def tearDown(self):self.client.__exit__(None,None,None);self.tmp.cleanup()
 def request(self,method,path,**kw):return self.client.request(method,path,headers=self.headers,**kw)
 def create(self,mode='simulation',profile='moderate_likelihood'):
  r=self.request('POST','/sessions',json={'name':'Test child','age':24,'relationship':'Parent','mode':mode,'profile':profile,'consent':True});self.assertEqual(r.status_code,200,r.text);return r.json()
 def mutate(self,s,path,body=None,method='POST'):
  return self.request(method,f"/sessions/{s['id']}"+path,json={'revision':s['revision'],'request_id':str(uuid.uuid4()),**(body or {})})
 def complete(self,s):
  for _ in range(20):
   r=self.mutate(s,'/control',{'action':'step'});self.assertEqual(r.status_code,200,r.text);s=r.json()
  return s
 def generate(self,s):
  r=self.mutate(s,'/reports');self.assertEqual(r.status_code,200,r.text)
  for _ in range(100):
   s=self.request('GET','/sessions/'+s['id']).json()
   if s['report_status']!='generating':break
   time.sleep(.01)
  self.assertEqual(s['report_status'],'ready',s.get('report_error'))
  rid=s['reports'][-1]['id'];return s,self.request('GET',f"/sessions/{s['id']}/reports/{rid}").json()
 def test_auth_ownership_consent(self):
  self.assertEqual(self.client.get('/health').status_code,403)
  s=self.create();other={**self.headers,'x-owner':str(uuid.uuid4())}
  self.assertEqual(self.client.get('/sessions/'+s['id'],headers=other).status_code,404)
  self.assertEqual(self.request('POST','/sessions',json={'name':'A','age':24,'relationship':'Parent'}).status_code,422)
 def test_pause_retry_revision_and_confirm(self):
  s=self.create('interactive');body={'revision':s['revision'],'request_id':str(uuid.uuid4()),'text':'Yesterday he looked, but I am not sure.'}
  r=self.request('POST',f"/sessions/{s['id']}/turns",json=body);self.assertEqual(r.status_code,200,r.text);s=r.json()
  self.assertEqual(s['current_question']['id'],1);self.assertEqual(s['pending']['suggested'],'unknown');self.assertEqual(s['answers'],{})
  repeated=self.request('POST',f"/sessions/{s['id']}/turns",json=body).json();self.assertEqual(repeated['revision'],s['revision'])
  bad=self.mutate({**s,'revision':0},'/control',{'action':'pause'});self.assertEqual(bad.status_code,409)
  s=self.mutate(s,'/control',{'action':'pause'}).json();self.assertEqual(self.mutate(s,'/answers/1',{'value':'yes'},'PATCH').status_code,409)
  s=self.mutate(s,'/control',{'action':'resume'}).json();s=self.mutate(s,'/answers/1',{'value':'unknown'},'PATCH').json();self.assertEqual(s['current_question']['id'],2);self.assertEqual(s['score']['band'],'INCOMPLETE')
 def test_clarification_stays_on_question(self):
  s=self.create('interactive')
  s=self.mutate(s,'/turns',{'text':'I am unsure.'}).json()
  s=self.mutate(s,'/turns',{'text':'Sometimes he looks at my hand instead.'}).json()
  self.assertEqual(s['current_question']['id'],1)
  self.assertEqual(s['answers'],{})
  self.assertEqual(len([t for t in s['turns'] if t['role']=='caregiver']),2)
  s=self.mutate(s,'/answers/1',{'value':'unknown'},'PATCH').json()
  self.assertEqual(s['current_question']['id'],2)
 def test_q20_requires_response(self):
  s=self.create()
  for _ in range(19):s=self.mutate(s,'/control',{'action':'step'}).json()
  self.assertEqual(s['current_question']['id'],20)
  self.assertEqual(s['status'],'running')
  self.assertEqual(self.mutate(s,'/reports').status_code,409)
 def test_report_failure_and_restart_recovery(self):
  s=self.complete(self.create())
  s['owner']=self.headers['x-owner'];s['requests']=[];s['reports']=[];s['report_status']='generating'
  self.app.state.store.put(s)
  self.app.state.store.recover()
  self.assertEqual(self.request('GET','/sessions/'+s['id']).json()['report_status'],'failed')
 def test_failed_provider_does_not_advance(self):
  s=self.create('interactive');self.provider.fail=True
  self.assertEqual(self.mutate(s,'/turns',{'text':'A test response'}).status_code,502)
  loaded=self.request('GET','/sessions/'+s['id']).json();self.assertEqual(loaded['revision'],0);self.assertEqual(len(loaded['turns']),2)
 def test_complete_report_pdf_stale_and_delete(self):
  s=self.create();self.assertEqual(self.mutate(s,'/reports').status_code,409)
  s=self.complete(s);self.assertEqual(s['status'],'complete');self.assertEqual(s['score']['total'],6);self.assertEqual(s['score']['followup'],'pending')
  s,r=self.generate(s);self.assertEqual(len(r['analysis']['criteria']),7)
  path=f"/sessions/{s['id']}/reports/{r['id']}/pdf";pdf=self.request('GET',path)
  self.assertEqual(pdf.status_code,200,pdf.text if pdf.status_code!=200 else '');self.assertTrue(pdf.content.startswith(b'%PDF'))
  Path('/private/tmp/asdwise-plan/haven-demo-report.pdf').write_bytes(pdf.content)
  s=self.mutate(s,'/answers/1',{'value':'unknown'},'PATCH').json();self.assertIsNone(s['score']['total']);self.assertEqual(self.request('GET',path).status_code,409)
  s,r=self.generate(s);self.assertEqual(r['score']['band'],'INCOMPLETE')
  self.request('DELETE','/sessions/'+s['id']);self.assertEqual(self.request('GET','/sessions/'+s['id']).status_code,404)
 def test_context_and_voice(self):
  s=self.create('interactive')
  headers={**self.headers,'content-type':'audio/webm'}
  r=self.client.post(f"/sessions/{s['id']}/audio/transcriptions",headers=headers,content=b'x'*500)
  self.assertEqual(r.status_code,200);self.assertEqual(self.request('GET','/sessions/'+s['id']).json()['answers'],{})
  self.assertEqual(self.client.post(f"/sessions/{s['id']}/audio/transcriptions",headers={**headers,'content-type':'text/plain'},content=b'x'*500).status_code,415)
  s=self.mutate(s,'/context',{'onset':'At 20 months','impact':'At home','routines':'Unknown','interests':'Unknown'},'PATCH').json()
  self.assertEqual(s['context']['onset'],'At 20 months')
  s=self.mutate(s,'/context',{'onset':'At 22 months'},'PATCH').json()
  self.assertTrue(any(t['role']=='superseded' for t in s['turns']))
 def test_reference_and_quote_validation(self):
  s=self.complete(self.create());ref=reports.reference();a=reports.demo_analysis(s,ref)
  a['criteria'][0]['evidence'][0]['quote']='Invented caregiver quote'
  with self.assertRaises(ValueError):reports.validate_analysis(a,s,ref)
  a=reports.demo_analysis(s,ref);a['criteria'][0]['source_pages']=[999]
  with self.assertRaises(ValueError):reports.validate_analysis(a,s,ref)
  a=reports.demo_analysis(s,ref);a['criteria'][0]['status']='reported concern';a['criteria'][1]['status']='reported concern';a['criteria'][1]['evidence']=[a['criteria'][0]['evidence'][0]]
  with self.assertRaises(ValueError):reports.validate_analysis(a,s,ref)
 def test_database_encryption_and_reload(self):
  s=self.create();raw=(Path(self.tmp.name)/'sessions.sqlite3').read_bytes();self.assertNotIn(b'Liam',raw)
  from web.store import Store
  reopened=Store(self.tmp.name);self.assertEqual(reopened.get(s['id'],self.headers['x-owner'])['child']['name'],'Liam')
 def test_three_profiles(self):
  for p in ['low_likelihood','moderate_likelihood','high_likelihood']:
   s=self.complete(self.create(profile=p));self.assertEqual(s['score']['band'],{'low_likelihood':'LOW','moderate_likelihood':'MODERATE','high_likelihood':'HIGH'}[p])

if __name__=='__main__':unittest.main()
