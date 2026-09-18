"""Opt-in live UX checks using FICTIONAL data only; never run in normal tests.
Run with PYTHONPATH=src and ASDWISE_ENV_FILE pointing to a private dotenv file.
Writes fictional test observations, not real caregiver data, to an explicit output path.
"""
import argparse, asyncio, copy, json, os, time, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from web.api import create_app
from web.providers import Provider
from web import reports

ROOT=Path(__file__).resolve().parents[2]
NARRATIVE_ITEMS={1,3,8,10,12,19}

def scenarios():
 specs=[
  ('daycare','moderate_likelihood','Daycare educator','Fictional Casey',24,
   'I am the daycare educator. I see this child in a group classroom on weekdays; I cannot speak for home. ',
   {'onset':'I have known this child for eight weeks and cannot describe earlier development.', 'impact':'In our classroom, joining group play and moving between activities sometimes require individual support. I do not know how things go at home.', 'routines':'At daycare, an unexpected change from outdoor play to circle time sometimes leads to crying for several minutes. A picture schedule helps.', 'interests':'In class, this child enjoys cars but also uses blocks and paint. I cannot describe interests at home.'}),
  ('mom','high_likelihood','Mother','Fictional Jordan',22,
   'I am the mother and care for my child most days at home. ',
   {'onset':'I first noticed these patterns around 18 months, but I am uncertain about the exact timing.', 'impact':'At home, communicating needs and joining family play are difficult. I feel worried and would like practical next steps rather than a diagnosis from this tool.', 'routines':'Changing our familiar route to the playground often leads to crying and difficulty settling for about ten minutes.', 'interests':'At home, spinning toy wheels holds attention for long periods, and shifting to meals often needs repeated support.'}),
  ('dad','low_likelihood','Father','Fictional Riley',20,
   'I am the father. Most of my observations are from evenings and weekends, when we play one-to-one. ',
   {'onset':'I have not noticed a consistent change. My partner sees more weekday routines than I do.', 'impact':'One-to-one play at home usually goes smoothly. My partner reports more difficulty responding during busy routines; I do not see those situations often.', 'routines':'During weekends my child usually accepts a change after a short explanation. I cannot describe daycare transitions.', 'interests':'My child chooses several kinds of toys during our play and usually shifts between them.'})]
 result=[]
 for key,base,role,name,age,prefix,context in specs:
  profile=json.loads((ROOT/'src/profiles'/f'{base}.json').read_text())
  answers={int(k.split('_')[0]):dict(v) for k,v in profile['behaviors'].items()}
  for q in NARRATIVE_ITEMS:answers[q]['detail']=prefix+answers[q]['detail']
  if key=='daycare':
   answers[2]={'response':'unknown','detail':'I do not know whether the parents have worried about hearing.'}
   answers[20]={'response':'unknown','detail':'We do not swing or bounce children in my classroom, so I cannot answer from observation.'}
   answers[19]={'response':'unknown','detail':prefix+'I have not seen enough unfamiliar situations to answer this reliably.'}
  if key=='dad':
   answers[10]['detail']=prefix+'My child usually looks when I call during quiet play. My partner says this happens less during busy routines. Should I report what I see or what my partner sees?'
  result.append(dict(key=key,role=role,name=name,age=age,answers=answers,context=context))
 return result

class ObservedProvider(Provider):
 def __init__(self):super().__init__();self.events=[]
 async def guide(self,s,text):
  start=time.monotonic()
  try:
   reply=await super().guide(s,text)
   self.events.append({'type':'guide','question':s['current_question']['id'],'seconds':round(time.monotonic()-start,2),'input':text,**reply})
   return reply
  except Exception as e:
   self.events.append({'type':'guide_error','question':s['current_question']['id'],'error_type':type(e).__name__})
   raise
 async def evaluate(self,s,ref):
  start=time.monotonic()
  try:
   result=await super().evaluate(s,ref)
   try:reports.validate_analysis(copy.deepcopy(result),s,ref)
   except ValueError as e:self.events.append({'type':'validation_error','reason':str(e)})
   self.events.append({'type':'evaluate','seconds':round(time.monotonic()-start,2)})
   return result
  except Exception as e:
   self.events.append({'type':'evaluate_error','error_type':type(e).__name__})
   raise

def run(spec):
 start=time.monotonic();p=ObservedProvider();out={'fictional':True,'persona':spec['key'],'relationship':spec['role'],'checks':{},'events':p.events}
 app=create_app(provider=p,gateway_secret='fictional-ux-check')
 with TestClient(app) as c:
  h={'x-gateway-secret':'fictional-ux-check','x-owner':str(uuid.uuid4())}
  def request(method,path,body=None):
   r=c.request(method,path,json=body,headers=h)
   if r.status_code!=200:raise RuntimeError(f'HTTP {r.status_code} at {path}')
   return r.json()
  s=request('POST','/sessions',{'name':spec['name'],'age':spec['age'],'relationship':spec['role'],'consent':True})
  sid=s['id']
  def mutation(path,body=None,method='POST'):
   return request(method,'/sessions/'+sid+path,{'revision':s['revision'],'request_id':str(uuid.uuid4()),**(body or {})})
  try:
   for q in range(1,21):
    if q in NARRATIVE_ITEMS:
     try:
      s=mutation('/turns',{'text':spec['answers'][q]['detail']})
      assert s['current_question']['id']==q and str(q) not in s['answers']
     except RuntimeError as e:out.setdefault('failures',[]).append(str(e))
    s=mutation('/answers/'+str(q),{'value':spec['answers'][q]['response']},'PATCH')
    if q==8:
     s=mutation('/control',{'action':'pause'})
     assert s['status']=='paused'
     s=mutation('/control',{'action':'resume'})
    if q%5==0:print(spec['key']+': '+str(q)+'/20 confirmed',flush=True)
   out['checks']['completed_20']=s['status']=='complete' and len(s['answers'])==20
   out['score']=s['score'];out['checks']['pause_resume']=True
   if spec['key']=='daycare':out['checks']['uncertainty_preserved']=s['score']['total'] is None and s['score']['band']=='INCOMPLETE'
   s=mutation('/context',spec['context'],'PATCH')
   s=mutation('/reports')
   for _ in range(180):
    time.sleep(3)
    s=request('GET','/sessions/'+sid)
    if s['report_status']!='generating':break
   out['checks']['report_ready']=s['report_status']=='ready'
   if s['reports']:
    rid=s['reports'][-1]['id'];r=request('GET',f'/sessions/{sid}/reports/{rid}')
    out['report']=r
    pdf=c.get(f'/sessions/{sid}/reports/{rid}/pdf',headers=h)
    out['checks']['pdf_download']=pdf.status_code==200 and pdf.content.startswith(b'%PDF')
   else:out['report_error']=s.get('report_error')
  except Exception as e:out.setdefault('failures',[]).append(type(e).__name__+': '+str(e))
  finally:
   request('DELETE','/sessions/'+sid)
   out['checks']['cleared']=c.get('/sessions/'+sid,headers=h).status_code==404 and not app.state.store.sessions
 out['seconds']=round(time.monotonic()-start,2)
 print(spec['key']+': '+json.dumps(out['checks']),flush=True)
 return out

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
 if not os.environ.get('ASDWISE_ENV_FILE'):raise SystemExit('Set ASDWISE_ENV_FILE; never pass a key as a command argument.')
 load_dotenv(os.environ['ASDWISE_ENV_FILE'])
 if not os.getenv('OPENAI_API_KEY'):raise SystemExit('Configured key is missing.')
 with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,scenarios()))
 Path(args.output).parent.mkdir(parents=True,exist_ok=True)
 Path(args.output).write_text(json.dumps({'method':'Fictional UX walkthrough: six live narrative interactions and fourteen confirmed quick answers per persona; live evaluator; no human participants.','results':results},indent=2))
 print('FICTIONAL_RESULTS_WRITTEN',flush=True)
 if any(r.get('failures') or not all(r['checks'].values()) for r in results):raise SystemExit(1)
