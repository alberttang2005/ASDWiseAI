"""Behavioral regression tests: no live provider calls or patient data."""
import copy, json, tempfile, time, unittest, uuid
from pathlib import Path
from fastapi.testclient import TestClient
from web.api import create_app
from web.domain import QUESTIONS, SCORER, score, CRITERIA
from web import reports

def demo_analysis(session,ref):
 # Offline mode intentionally avoids invented clinical judgments.
 criteria=[]
 for code,(title,pages) in CRITERIA.items():
  related={q['id'] for q in QUESTIONS if code in q['dsm5_mapping']} if code not in ('B2','B3') else set()
  turns=[t for t in session['turns'] if t['role']=='caregiver' and t.get('question_id') in related][:2]
  criteria.append({'code':code,'title':title,'status':'insufficient evidence','interpretation':'This offline demonstration displays relevant recorded observations without making an AI clinical interpretation. A source-grounded evaluation requires a configured provider and review.',
    'evidence':[{'turn_id':t['id'],'question_id':t.get('question_id'),'quote':t['text'],'interpretation':'Recorded caregiver observation; not sufficient by itself to establish a diagnostic criterion.'} for t in turns],
    'source_pages':pages,'missing_context':'Frequency, multiple settings, developmental context, and impact require review.'})
 return {'criteria':criteria,'summary':'Synthetic demonstration only. The initial score summarizes the selected profile; criterion-level clinical conclusions have not been generated.', 'strengths':[], 'limitations':['Offline template; no AI clinical analysis performed.','The screening does not establish diagnosis or severity.']}

class FakeProvider:
 enabled=True
 evaluator_model='test-provider'
 fail=False
 async def guide(self,s,text):
  if self.fail:raise RuntimeError('provider unavailable')
  return {'response':'Could you tell me what happens most often?','suggested_answer':'unknown'}
 async def evaluate(self,s,ref):return demo_analysis(s,ref)
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
 def create(self,mode='interactive',profile='moderate_likelihood'):
  self.profile=profile
  r=self.request('POST','/sessions',json={'name':'Liam','age':24,'relationship':'Parent','mode':mode,'consent':True});self.assertEqual(r.status_code,200,r.text);return r.json()
 def mutate(self,s,path,body=None,method='POST'):
  return self.request(method,f"/sessions/{s['id']}"+path,json={'revision':s['revision'],'request_id':str(uuid.uuid4()),**(body or {})})
 def step(self,s):
  profile=json.loads((Path(__file__).resolve().parents[1]/'src/profiles'/f'{self.profile}.json').read_text())
  q=s['current_question']['id'];behavior=next(v for k,v in profile['behaviors'].items() if k.startswith(str(q)+'_'))
  r=self.mutate(s,'/turns',{'text':behavior['detail']});self.assertEqual(r.status_code,200,r.text)
  r=self.mutate(r.json(),f'/answers/{q}',{'value':behavior['response']},'PATCH');self.assertEqual(r.status_code,200,r.text)
  return r.json()
 def complete(self,s):
  for _ in range(20):s=self.step(s)
  return s
 def test_demo_rejected_and_unavailable_no_fallback(self):
  body={'name':'Test','age':24,'relationship':'Parent','consent':True}
  self.assertEqual(self.request('POST','/sessions',json={**body,'mode':'simulation'}).status_code,422)
  s=self.create()
  self.assertEqual(self.mutate(s,'/control',{'action':'step'}).status_code,422)
  self.provider.enabled=False
  self.assertEqual(self.request('POST','/sessions',json=body).status_code,503)
 def test_session_extension_preserves_answers_and_report_revision(self):
  s=self.create()
  s=self.mutate(s,'/answers/1',{'value':'unknown'},'PATCH').json()
  s=self.mutate(s,'/control',{'action':'pause'}).json()
  original_expiry=s['expires_at']
  r=self.mutate(s,'/control',{'action':'keepalive'})
  self.assertEqual(r.status_code,200)
  renewed=r.json()
  self.assertGreaterEqual(renewed['expires_at'],original_expiry)
  self.assertEqual(renewed['revision'],s['revision'])
  self.assertEqual(renewed['answers'],s['answers'])
  self.assertEqual(renewed['status'],'paused')
  self.assertEqual(renewed['score']['items'][0]['text'],QUESTIONS[0]['text'])
  self.assertEqual(renewed['score']['band'],'INCOMPLETE')
 def test_expired_session_cannot_be_extended(self):
  s=self.create()
  self.app.state.store.sessions[s['id']]=(time.monotonic()-1801,s)
  self.assertEqual(self.mutate(s,'/control',{'action':'keepalive'}).status_code,404)
 def test_age_and_blank_context_validation(self):
  for extra in [{'age':15},{'age':31},{'name':' '},{'relationship':' '}]:
   body={'name':'Test','age':24,'relationship':'Parent','consent':True,**extra}
   self.assertEqual(self.request('POST','/sessions',json=body).status_code,422)
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
  for _ in range(19):s=self.step(s)
  self.assertEqual(s['current_question']['id'],20)
  self.assertEqual(s['status'],'running')
  self.assertEqual(self.mutate(s,'/reports').status_code,409)
 def test_restart_does_not_recover_data(self):
  from web.store import Store
  s=self.create()
  self.assertIsNone(Store().get(s['id'],self.headers['x-owner']))
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
  s=self.complete(self.create());ref=reports.reference();a=demo_analysis(s,ref)
  a['criteria'][0]['evidence'][0]['quote']='Invented caregiver quote'
  with self.assertRaises(ValueError):reports.validate_analysis(a,s,ref)
  a=demo_analysis(s,ref);a['criteria'][0]['source_pages']=[999]
  with self.assertRaises(ValueError):reports.validate_analysis(a,s,ref)
  a=demo_analysis(s,ref);a['criteria'][0]['status']='reported concern';a['criteria'][1]['status']='reported concern';a['criteria'][1]['evidence']=[a['criteria'][0]['evidence'][0]]
  with self.assertRaises(ValueError):reports.validate_analysis(a,s,ref)
 def test_criterion_order_and_missing_criteria(self):
  s=self.complete(self.create());ref=reports.reference();a=demo_analysis(s,ref)
  a['criteria'].reverse()
  self.assertEqual([c['code'] for c in reports.validate_analysis(a,s,ref)['criteria']],list(CRITERIA))
  a['criteria'].pop()
  with self.assertRaises(ValueError):reports.validate_analysis(a,s,ref)
 def test_memory_storage_expiry_and_no_disk_files(self):
  from web.store import Store
  from unittest.mock import patch
  s=self.create()
  self.assertEqual(list(Path(self.tmp.name).iterdir()),[])
  with patch('web.store.time.monotonic',return_value=time.monotonic()+1801):
   self.assertIsNone(self.app.state.store.get(s['id'],self.headers['x-owner']))
 def test_report_timeout_preserves_answers_and_retries(self):
  import asyncio
  s=self.complete(self.create());answers=copy.deepcopy(s['answers'])
  original=self.provider.evaluate
  async def slow(*args):await asyncio.sleep(1)
  self.provider.evaluate=slow;self.app.state.report_timeout=.02
  self.assertEqual(self.mutate(s,'/reports').status_code,200)
  for _ in range(50):
   time.sleep(.01);s=self.request('GET','/sessions/'+s['id']).json()
   if s['report_status']=='failed':break
  self.assertEqual(s['report_error_code'],'timeout')
  self.assertEqual(s['answers'],answers);self.assertEqual(s['reports'],[])
  self.provider.evaluate=original;self.app.state.report_timeout=120
  s,r=self.generate(s)
  self.assertEqual(s['answers'],answers);self.assertEqual(len(s['reports']),1)
 def test_observation_context_and_differences_reach_report(self):
  scope={'setting':'Home during quiet play','frequency':'Evenings and weekends','familiarity':'Since birth'}
  self.profile='low_likelihood'
  r=self.request('POST','/sessions',json={'name':'Fictional Riley','age':20,'relationship':'Father','observation_context':scope,'consent':True})
  self.assertEqual(r.status_code,200)
  s=self.complete(r.json());score_before=s['score']['total']
  difference='My partner reports less response during busy routines. I usually see a response in quiet play.'
  s=self.mutate(s,'/context',{'other_observations':difference},'PATCH').json()
  s,report=self.generate(s)
  self.assertEqual(report['observation_context'],scope)
  self.assertEqual(report['context']['other_observations'],difference)
  self.assertEqual(report['score']['total'],score_before)
  self.assertEqual(report['child']['relationship'],'Father')
 def test_three_profiles(self):
  for p in ['low_likelihood','moderate_likelihood','high_likelihood']:
   self.headers['x-owner']=str(uuid.uuid4())
   s=self.complete(self.create(profile=p));self.assertEqual(s['score']['band'],{'low_likelihood':'LOW','moderate_likelihood':'MODERATE','high_likelihood':'HIGH'}[p])

class GuideFocusTests(unittest.TestCase):
 def test_identity_and_detour_questions_are_not_shown(self):
  from web.providers import focused_reply
  for response in ["You said she but are listed as the father. Could you confirm her pronouns?", "Would you like a checklist?", "Shall I make a template?"]:
   r=focused_reply({'response':response,'suggested_answer':'yes'})
   self.assertEqual(r['suggested_answer'],'unknown')
   self.assertIn('personally observed',r['response'])
 def test_evidence_selection_keeps_exact_words_and_rejects_invented_id(self):
  from web.providers import materialize_evidence
  catalog={'E1':{'id':'original-turn','role':'caregiver','text':'She looks at me. My partner reports something different.'}}
  source={'criteria':[{'code':code,'status':'insufficient evidence','interpretation':'More context is needed.','evidence':[{'evidence_id':'E1','interpretation':'Recorded words.'}],'missing_context':'Other settings'} for code in CRITERIA],'summary':'A caregiver account.','strengths':[],'limitations':[]}
  result=materialize_evidence(copy.deepcopy(source),catalog)
  self.assertEqual(result['criteria'][0]['evidence'][0]['quote'],catalog['E1']['text'])
  self.assertEqual(result['criteria'][0]['evidence'][0]['turn_id'],'original-turn')
  self.assertEqual(result['criteria'][0]['source_pages'],CRITERIA['A1'][1])
  source['criteria'][0]['evidence'][0]['evidence_id']='invented'
  with self.assertRaises(ValueError):materialize_evidence(source,catalog)
 def test_evaluator_validation_retry_is_bounded(self):
  import asyncio
  from web.providers import Provider
  from unittest.mock import AsyncMock
  s={'turns':[]};ref=reports.reference();valid=demo_analysis(s,ref)
  p=Provider.__new__(Provider)
  p._evaluate_once=AsyncMock(side_effect=[ValueError('Unknown caregiver evidence ID'),copy.deepcopy(valid)])
  self.assertEqual(len(asyncio.run(p.evaluate(s,ref))['criteria']),7)
  self.assertEqual(p._evaluate_once.await_count,2)
  self.assertEqual(p._evaluate_once.await_args.args[2],'Unknown caregiver evidence ID')
  p._evaluate_once=AsyncMock(side_effect=ValueError('Unknown caregiver evidence ID'))
  with self.assertRaises(ValueError):asyncio.run(p.evaluate(s,ref))
  self.assertEqual(p._evaluate_once.await_count,2)
 def test_no_pressure_when_caregiver_has_not_observed_enough(self):
  import asyncio
  from web.providers import Provider
  p=Provider.__new__(Provider)
  result=asyncio.run(p.guide({'current_question':QUESTIONS[18]},'I have not seen enough unfamiliar situations to answer reliably.'))
  self.assertEqual(result['suggested_answer'],'unknown')
  self.assertNotIn('?',result['response'])
 def test_clear_observation_does_not_trigger_other_settings_question(self):
  from web.providers import focused_reply
  r=focused_reply({'response':'She looks to you during weekend play. Can you describe other settings?', 'suggested_answer':'unknown'})
  self.assertEqual(r['response'],'She looks to you during weekend play.')
 def test_normal_daughter_observation_is_preserved(self):
  from web.providers import focused_reply
  reply={'response':'Your daughter usually looks when you point during quiet play.','suggested_answer':'yes'}
  self.assertEqual(focused_reply(reply),reply)

if __name__=='__main__':unittest.main()
