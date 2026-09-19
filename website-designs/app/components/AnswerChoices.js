'use client';
import {useState} from 'react';

export default function AnswerChoices({question, busy, onConfirm, pending, hasDraft}) {
 const [choice,setChoice]=useState('');
 return <section className="answer-confirmation" aria-label="Record your answer">
  <h3>{pending?'Confirm your answer':'Choose your answer'}</h3>
  {pending&&<p className="confirm-question">Your answer is for: <strong>{question.text}</strong></p>}
  <fieldset className="answer-options" disabled={busy}>
   <legend>Which response fits best?</legend>
   {[['yes','Yes'],['no','No'],['unknown','Not sure']].map(([value,label])=><label key={value} className={choice===value?'selected':''}>
    <input type="radio" name={`answer-${question.id}`} value={value} checked={choice===value} onChange={()=>setChoice(value)}/>{label}
   </label>)}
  </fieldset>
  {choice==='unknown'&&<p className="uncertain-note">It’s okay to be unsure. You can ask for help above or keep this answer as “Not sure” and revisit it before finishing.</p>}
  {hasDraft&&<p className="muted-copy">You have an unsent example. Send it above to include it, or clear it before continuing.</p>}
  <div className="confirm-actions"><span>Your selection is recorded only when you continue.</span><button className="primary" disabled={busy||!choice||hasDraft} onClick={()=>onConfirm(choice)}>{busy?'Recording…':choice==='unknown'?'Keep as not sure & continue →':'Confirm & continue →'}</button></div>
 </section>
}
