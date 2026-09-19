'use client';
import {useEffect,useRef,useState} from 'react';

function AnswerRow({item,session,busy,onChange,highlight}) {
 const answer=session.answers[item.id];
 const observation=session.turns.find(t=>t.id===answer?.turn_id);
 return <article className={`review-answer ${highlight?'highlight':''}`} id={`review-question-${item.id}`} tabIndex={-1}>
  <div><span className="eyebrow">QUESTION {item.id}</span><h3>{item.text||item.label}</h3>
   {observation&&observation.modality!=='selection'&&<details><summary>Your original observation</summary><blockquote>{observation.text}</blockquote></details>}
  </div>
  {answer?<label>Recorded answer<select aria-label={`Answer to ${item.label}`} value={answer.value} disabled={busy||['paused','stopped'].includes(session.status)} onChange={e=>onChange(item.id,e.target.value)}><option value="yes">Yes</option><option value="no">No</option><option value="unknown">Not sure</option></select></label>:<span className="status-chip">Not answered yet</span>}
 </article>
}

export default function Review({session,busy,context,setContext,mutate,onReturn,onOpenReport,focusQuestion}) {
 const [saved,setSaved]=useState('');
 const [filter,setFilter]=useState(focusQuestion?'all':'attention');
 const top=useRef(null);
 const [clock,setClock]=useState(Date.now());
 useEffect(()=>{if(session.report_status!=='generating')return;const timer=setInterval(()=>setClock(Date.now()),1000);return()=>clearInterval(timer)},[session.report_status]);
 const seconds=session.report_started_at?Math.max(0,Math.floor(clock/1000-session.report_started_at)):0;
 const items=session.score.items;
 const unanswered=items.filter(q=>!session.answers[q.id]);
 const uncertain=items.filter(q=>session.answers[q.id]?.value==='unknown');
 const attention=items.filter(q=>!session.answers[q.id]||session.answers[q.id].value==='unknown');
 const dirty=JSON.stringify(context)!==JSON.stringify(session.context);
 const latest=[...session.reports].reverse().find(r=>r.revision===session.revision);
 useEffect(()=>{if(focusQuestion){document.getElementById(`review-question-${focusQuestion}`)?.focus()}else{top.current?.focus()}},[focusQuestion]);
 async function change(id,value){setSaved('');const ok=await mutate(`/answers/${id}`,{value},'PATCH');if(ok)setSaved(`Question ${id} updated.`)}
 return <section className="review">
  <div className="eyebrow">REVIEW YOUR RESPONSES</div><h1 ref={top} tabIndex={-1}>A moment to review.</h1>
  <p>You can change any answer. It’s okay to leave something as “Not sure.”</p>
  <div className="review-stats"><span><strong>{Object.keys(session.answers).length}</strong> of 20 recorded</span><span><strong>{uncertain.length}</strong> not sure</span><span><strong>{unanswered.length}</strong> not answered</span></div>
  {session.status==='paused'&&<div className="notice">Your interview is paused. Return and resume to edit answers.</div>}
  <div className="review-next">
   <div><h2>{unanswered.length?'Continue your conversation':uncertain.length?`${uncertain.length} ${uncertain.length===1?'answer':'answers'} to revisit`:'Ready when you are'}</h2>
    <p>{unanswered.length?'Finish the remaining questions before creating your report.':uncertain.length?'Review the uncertain answers below, or create a report that clearly marks them as unresolved. A final screening classification is unavailable while answers remain uncertain.':'Check your answers below or create your report.'}</p></div>
   {session.status!=='complete'?<button className="primary" onClick={onReturn}>Return to interview →</button>:<button className="primary" disabled={busy||dirty||session.report_status==='generating'} onClick={()=>mutate('/reports')}>{session.report_status==='generating'?'Preparing report…':session.report_error?'Retry report →':uncertain.length?'Create report with uncertainty →':'Create my report →'}</button>}
  </div>
  {dirty&&<p className="notice">Apply or discard your additional context below before creating a report.</p>}
  {session.report_status==='generating'&&<div className="notice" role="status"><strong>Your report is being prepared.</strong><p aria-live="off">{seconds} seconds elapsed{seconds>=120?" · Waiting for the server’s final status…":""}</p><p>We’re organizing your responses and checking their evidence. Keep this tab open. This attempt has a two-minute limit; if it times out, you can retry with your answers intact.</p><button className="secondary" disabled={busy} onClick={()=>mutate('/control',{action:'keepalive'})}>Keep session open</button></div>}
  {session.report_error&&<div className="notice error" role="alert"><strong>{session.report_error_code==='timeout'?'The report took too long.':'We couldn’t prepare your report.'}</strong><p>{session.report_error} Your responses are still available in this session. Try again using “Retry report” above.</p></div>}
  {latest&&session.report_status!=='generating'&&<div className="report-ready" role="status"><div><h2>Your report is ready.</h2><p>Open it and download a copy before leaving this page.</p></div><button className="primary" disabled={busy} onClick={()=>onOpenReport(latest.id)}>Open my report →</button></div>}
  <div className="review-filters" role="group" aria-label="Choose responses to review"><button className="secondary" aria-pressed={filter==='attention'} onClick={()=>setFilter('attention')}>To revisit ({attention.length})</button><button className="secondary" aria-pressed={filter==='all'} onClick={()=>setFilter('all')}>All questions (20)</button></div>
  <p className="save-feedback" role="status">{saved}</p>
  {filter==='attention'&&!attention.length&&<p className="notice">Every question has a Yes or No answer. Choose “All questions” to make any changes.</p>}
  {(filter==='all'?items:attention).map(item=><AnswerRow key={item.id} item={item} session={session} busy={busy} onChange={change} highlight={item.id===focusQuestion}/>)}
  <details className="criterion optional-context"><summary>Add more context (optional)</summary><p>Share anything else you’d like your care team to know. This does not change the 20-question score.</p>{[['onset','When did you first notice these patterns?'],['impact','How do they affect daily life, and in which settings?'],['routines','What happens when routines or plans change?'],['interests','Are any interests unusually intense or difficult to shift from?'],['other_observations','Do other caregivers notice something different? Say who observed it, where, and whether they told you or you saw it yourself.']].map(([key,label])=><label key={key}>{label}<textarea maxLength={2000} value={context[key]} disabled={busy} onChange={e=>setContext({...context,[key]:e.target.value})}/></label>)}<div className="context-actions"><button className="secondary" disabled={busy||!dirty} onClick={async()=>{const ok=await mutate('/context',context,'PATCH');if(ok)setSaved('Additional context applied.')}}>Apply additional context</button><button className="quiet" disabled={busy||!dirty} onClick={()=>setContext({...session.context})}>Discard changes</button></div></details>
  <button className="secondary" onClick={onReturn}>← Return to interview</button>
  {session.reports.some(r=>r.revision!==session.revision)&&<details className="history"><summary>Earlier reports</summary>{[...session.reports].reverse().filter(r=>r.revision!==session.revision).map(r=><button className="saved-row" key={r.id} onClick={()=>onOpenReport(r.id)}><span>{new Date(r.created).toLocaleString()}</span><span>Earlier responses</span><strong>Open report →</strong></button>)}</details>}
 </section>
}
