"""Source-grounded report validation and a shared PDF renderer."""
import json, re
from pathlib import Path
from io import BytesIO
from html import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from .domain import CRITERIA, QUESTIONS, DISCLAIMER, score

REFERENCE_PATH=Path(__file__).with_name('reference.json')
def reference():
 r=json.loads(REFERENCE_PATH.read_text())
 if not r.get('pages') or not r.get('sha256'):raise ValueError('Required DSM reference unavailable')
 return r

def validate_analysis(analysis,session,ref):
 codes=[c['code'] for c in analysis['criteria']]
 if len(codes)!=len(CRITERIA) or set(codes)!=set(CRITERIA):raise ValueError('Missing or duplicate criterion')
 analysis['criteria']=sorted(analysis['criteria'],key=lambda c:list(CRITERIA).index(c['code']))
 turns={t['id']:t for t in session['turns'] if t['role']=='caregiver'}
 pages={p['page'] for p in ref['pages']}
 used={}
 for c in analysis['criteria']:
  if not c['source_pages'] or not set(c['source_pages']) <= (set(CRITERIA[c['code']][1]) | {1}) or not set(c['source_pages'])<=pages:raise ValueError('Invalid source citation')
  if c['status']!='insufficient evidence' and not c['evidence']:raise ValueError('Unsupported criterion status')
  for e in c['evidence']:
   if e['turn_id'] not in turns or not e['quote'].strip() or e['quote'] not in turns[e['turn_id']]['text']:
    raise ValueError('Unverifiable caregiver quotation')
   if c['status']=='reported concern' and c['code'] in ('B2','B3'):
    expected_context = 'routines' if c['code']=='B2' else 'interests'
    if turns[e['turn_id']].get('context_key') != expected_context:
     raise ValueError('B2/B3 concerns need separate relevant supplemental observations')
   key=(e['turn_id'],e['quote'])
   if c['status']=='reported concern' and key in used:
    raise ValueError('Repeated evidence across concerns requires separate observations')
   if c['status']=='reported concern':used[key]=c['code']
  c['title']=CRITERIA[c['code']][0]
  for e in c['evidence']:e['question_id']=turns[e['turn_id']].get('question_id')
 # Conservative wording gate; human review remains required for clinical interpretation.
 text=json.dumps(analysis).lower()
 if re.search(r'\b(meets? (?:all |the )?(?:dsm|diagnostic)|diagnosed with autism|autism is confirmed|requires level [123])',text):
  raise ValueError('Diagnostic conclusion is not permitted in a screening report')
 return analysis

def assemble(session,analysis,ref,model):
 return {'session_id':session['id'],'child':session['child'],'mode':session['mode'],'revision':session['revision'],'score':score(session['answers']),
 'analysis':analysis,'observation_context':session.get('observation_context',{}),'context':session['context'],'model':model,'prompt_version':'haven-evaluator-2','instrument':'Project M-CHAT-R question set v2.0; initial screening only',
 'references':[{'title':ref['title'],'author':ref['author'],'date':ref['date'],'status':ref['status'],'sha256':ref['sha256']},ref['published_reference'],{'title':'Official M-CHAT-R/F scoring','url':'https://www.mchatscreen.com/mchat-rf/scoring/'}],
 'disclaimer':DISCLAIMER,'recommendations':{
 'Primary recommendation':score(session['answers'])['recommendation'],
 'Secondary recommendation':'Bring examples of everyday communication, play, routines, and sensory experiences to your care team. Discuss both strengths and concerns.',
 'Additional resources':'Official M-CHAT-R/F scoring guidance: mchatscreen.com/mchat-rf/scoring/. CDC autism screening guidance: cdc.gov/autism/diagnosis/. Ask your healthcare professional about local early intervention and evaluation options.',
 'Follow-up plan':'Discuss the appropriate follow-up and timing with your child’s healthcare professional. No appointment or referral has been scheduled by this application.'}}

def pdf(report):
 from .report_pdf import pdf as render_pdf
 return render_pdf(report)
