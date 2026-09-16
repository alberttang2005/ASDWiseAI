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
 if [c['code'] for c in analysis['criteria']]!=list(CRITERIA):raise ValueError('Missing or duplicate criterion')
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

def assemble(session,analysis,ref,model):
 return {'session_id':session['id'],'child':session['child'],'mode':session['mode'],'revision':session['revision'],'score':score(session['answers']),
 'analysis':analysis,'context':session['context'],'model':model,'prompt_version':'haven-evaluator-1','instrument':'Project M-CHAT-R question set v2.0; initial screening only',
 'references':[{'title':ref['title'],'author':ref['author'],'date':ref['date'],'status':ref['status'],'sha256':ref['sha256']},ref['published_reference'],{'title':'Official M-CHAT-R/F scoring','url':'https://www.mchatscreen.com/mchat-rf/scoring/'}],
 'disclaimer':DISCLAIMER,'recommendations':{
 'Primary recommendation':score(session['answers'])['recommendation'],
 'Secondary recommendation':'Bring examples of everyday communication, play, routines, and sensory experiences to your care team. Discuss both strengths and concerns.',
 'Additional resources':'The official M-CHAT-R/F scoring guidance and CDC clinical assessment overview are listed in References.',
 'Follow-up plan':'Discuss the appropriate follow-up and timing with your child’s healthcare professional. No appointment or referral has been scheduled by this application.'}}

def pdf(report):
 styles=getSampleStyleSheet()
 styles.add(ParagraphStyle(name='Haven',fontName='Helvetica',fontSize=10,leading=15,spaceAfter=8,textColor=colors.HexColor('#294638')))
 styles.add(ParagraphStyle(name='SmallHaven',parent=styles['Haven'],fontSize=8,leading=11))
 def p(t,style='Haven'):return Paragraph(escape(str(t)).replace('\n','<br/>'),styles[style])
 out=BytesIO();doc=SimpleDocTemplate(out,pagesize=(595,842),rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=45,title='ASDWise screening report',author='ASDWise')
 story=[p('ASDwise | Screening report','Title'),p(report['child']['name']+' · '+str(report['child']['age'])+' months'),p(report['created']+' · '+('SYNTHETIC DEMONSTRATION' if report['mode']=='simulation' else 'Caregiver interview')),p('Report '+report['id'][:8]+' · input revision '+str(report['revision']),'SmallHaven')]
 def heading(t):story.extend([Spacer(1,12),p(t,'Heading2')])
 heading('Initial screening summary')
 s=report['score'];story.extend([p(f"{s['total'] if s['total'] is not None else 'Incomplete'} / 20 · {s['band']}"),p('Formal Follow-Up: '+s['followup']),p(s['recommendation'])])
 heading('M-CHAT-R item responses')
 rows=[[p(x,'SmallHaven') for x in ['#','Item','Answer','Result']]]+[[p(x,'SmallHaven') for x in [q['id'],q['label'],q['answer'],q['result']]] for q in s['items']]
 t=Table(rows,colWidths=[25,220,78,188],repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7efe8')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#cddacf')),('LEFTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),5)]));story.append(t)
 story.append(PageBreak());heading('DSM-5-informed observations')
 for c in report['analysis']['criteria']:
  story.append(KeepTogether([p(c['code']+' — '+c['title'],'Heading3'),p(c['status'].capitalize()),p(c['interpretation'])]))
  for e in c['evidence']:
   story.append(KeepTogether([p(('Q'+str(e['question_id']) if e.get('question_id') else 'Supplemental context')+' · '+e['turn_id'][:8],'SmallHaven'),p('“'+e['quote']+'”'),p('Interpretation: '+e['interpretation'])]))
  story.extend([p('Missing context: '+c['missing_context']),p('Carpenter, February 2013, pp. '+', '.join(map(str,c['source_pages'])),'SmallHaven')])
 heading('Overall assessment');story.append(p(report['analysis']['summary']))
 for x in report['analysis']['strengths']:story.append(p('Strength: '+x))
 heading('Additional diagnostic context')
 for k,v in report['context'].items():story.append(p(k.capitalize()+': '+(v or 'Not reported')))
 story.append(p('Onset, functional impact, and alternative explanations require professional assessment. No diagnostic or severity determination is made.'))
 heading('Recommendations')
 for k,v in report['recommendations'].items():story.extend([p(k,'Heading3'),p(v)])
 story.append(PageBreak());heading('Limitations and references')
 for x in report['analysis']['limitations']:story.append(p(x))
 story.append(p(report['disclaimer']))
 for r in report['references']:story.append(p(' · '.join(str(r[k]) for k in ['title','author','date','status','url'] if k in r),'SmallHaven'))
 story.append(p('Model: '+report['model']+' · '+report['prompt_version'],'SmallHaven'))
 def footer(canvas,doc):
  canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#315e4b'));canvas.drawString(42,25,'ASDwise · Screening is not diagnosis');canvas.drawRightString(553,25,str(doc.page))
 doc.build(story,onFirstPage=footer,onLaterPages=footer)
 return out.getvalue()
