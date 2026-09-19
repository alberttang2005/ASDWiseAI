'use client';
import {useEffect,useState} from 'react';

export default function SessionNotice({session,busy,onKeepOpen,onExpired}) {
 const [now,setNow]=useState(()=>Date.now());
 useEffect(()=>{const tick=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(tick)},[]);
 const remaining=session.expires_at?Math.max(0,Math.ceil((session.expires_at*1000-now)/60000)):null;
 useEffect(()=>{if(remaining===0)onExpired()},[remaining,onExpired]);
 return <aside className={`session-notice ${remaining!==null&&remaining<=5?'expiring':''}`} aria-label="Temporary session">
  <div><strong>{remaining!==null&&remaining<=5?'Your session will expire soon':'This session stays in this tab'}</strong><p>{remaining!==null&&remaining<=5?`About ${remaining} ${remaining===1?'minute':'minutes'} left without an update. Keep it open to get another 30 minutes.`:'Closing or refreshing loses access to your progress. The session clears after 30 minutes without updates, even when paused.'}</p></div>
  {remaining!==null&&remaining<=5&&<button className="secondary" disabled={busy} onClick={onKeepOpen}>Keep session open</button>}
  <span className="sr-only" role="status">{remaining!==null&&remaining<=5?`Session expires in about ${remaining} minutes.`:''}</span>
 </aside>
}
