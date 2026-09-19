"""Validated interview and report contracts; scoring stays deterministic."""
import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from utils.mchat_scorer import MCHATScorer

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = json.loads((ROOT / 'data/mchat_questions.json').read_text())['questions']
SCORER = MCHATScorer()
CRITERIA = {
 'A1': ('Social-emotional reciprocity', [1,2]),
 'A2': ('Nonverbal communication', [2]),
 'A3': ('Developing and maintaining relationships', [2,3]),
 'B1': ('Repetitive movements, speech, or object use', [3,4]),
 'B2': ('Routines and resistance to change', [4]),
 'B3': ('Restricted interests', [4,5]),
 'B4': ('Sensory reactivity', [5]),
}
DISCLAIMER = 'This is a screening report, not a diagnosis. A positive screen does not establish autism, and a negative screen does not rule it out. Discuss observations with a qualified healthcare professional.'

class StrictModel(BaseModel):
 model_config = ConfigDict(extra='forbid')

class ObservationContext(StrictModel):
 setting: str = Field(default='', max_length=200)
 frequency: str = Field(default='', max_length=200)
 familiarity: str = Field(default='', max_length=200)

class SessionInput(StrictModel):
 name: str = Field(min_length=1, max_length=80)
 age: int = Field(ge=16, le=30)
 relationship: str = Field(min_length=1,max_length=60)
 observation_context: ObservationContext = Field(default_factory=ObservationContext)
 mode: Literal['interactive'] = 'interactive'
 consent: bool = False

class Mutation(StrictModel):
 revision: int = Field(ge=0)
 request_id: str = Field(min_length=8,max_length=100)

class TurnInput(Mutation):
 text: str = Field(min_length=1,max_length=6000)
 modality: Literal['text','voice'] = 'text'
 original_transcript: str = Field(default='',max_length=6000)

class AnswerInput(Mutation):
 value: Literal['yes','no','unknown']

class ControlInput(Mutation):
 action: Literal['pause','resume','stop','reset','keepalive']

class ContextInput(Mutation):
 onset: str = Field(default='',max_length=2000)
 impact: str = Field(default='',max_length=2000)
 routines: str = Field(default='',max_length=2000)
 interests: str = Field(default='',max_length=2000)
 other_observations: str = Field(default='',max_length=2000)

class GuideReply(StrictModel):
 response: str
 suggested_answer: Literal['yes','no','unknown']

class Evidence(StrictModel):
 turn_id: str
 quote: str
 interpretation: str

class CriterionAnalysis(StrictModel):
 code: Literal['A1','A2','A3','B1','B2','B3','B4']
 status: Literal['reported concern','no concern reported','insufficient evidence']
 interpretation: str
 evidence: list[Evidence]
 source_pages: list[int]
 missing_context: str

class Analysis(StrictModel):
 criteria: list[CriterionAnalysis] = Field(min_length=7, max_length=7)
 summary: str
 strengths: list[str]
 limitations: list[str]


def score(answers):
 normalized = {int(k): a['value'] for k,a in answers.items() if a['value'] in ('yes','no')}
 missing = [q['id'] for q in QUESTIONS if q['id'] not in normalized]
 raw = SCORER.score_responses(normalized)
 total = raw['total_score'] if not missing else None
 band = raw['risk_level'] if not missing else 'INCOMPLETE'
 followup = 'pending' if band == 'MODERATE' else 'not indicated by initial score' if band == 'LOW' else 'not required before referral' if band == 'HIGH' else 'awaiting complete responses'
 recommendation = {
 'INCOMPLETE': 'Review unanswered or uncertain items. A final screening classification cannot be calculated yet.',
 'LOW': 'No formal Follow-Up is indicated by this initial score. Discuss any developmental concerns with the care team; rescreen at 24 months if the child is younger than two.',
 'MODERATE': 'Arrange the formal M-CHAT-R Follow-Up for elevated-likelihood items. This application has not administered that instrument. If two or more items remain elevated after Follow-Up, the official algorithm recommends referral for early intervention and diagnostic evaluation.',
 'HIGH': 'The official algorithm recommends referral for early intervention and diagnostic evaluation without waiting for the formal Follow-Up.'
 }[band]
 return {'total':total,'band':band,'missing':missing,'answered':len(normalized),'followup':followup,'recommendation':recommendation,
 'items':[{'id':q['id'],'label':q['short_form'],'text':q['text'],'answer':answers.get(str(q['id']),{}).get('value','unanswered'),
 'result':'unresolved' if q['id'] not in normalized else 'elevated likelihood' if raw['item_scores'][q['id']] else 'low likelihood'} for q in QUESTIONS]}

class EvidenceSelection(StrictModel):
 evidence_id: str
 interpretation: str

class CriterionSelection(StrictModel):
 code: Literal['A1','A2','A3','B1','B2','B3','B4']
 status: Literal['reported concern','no concern reported','insufficient evidence']
 interpretation: str
 evidence: list[EvidenceSelection]
 missing_context: str

class SelectedAnalysis(StrictModel):
 criteria: list[CriterionSelection] = Field(min_length=7, max_length=7)
 summary: str
 strengths: list[str]
 limitations: list[str]
