'use client';
import {useEffect,useRef,useState} from 'react';
export default function VoiceControls({session,enabled,disabled,onTranscript,onError}) {
 const [state,setState]=useState('idle'),[seconds,setSeconds]=useState(0),[playing,setPlaying]=useState(false);
 const recorder=useRef(null),stream=useRef(null),chunks=useRef([]),cancelled=useRef(false),audio=useRef(null),url=useRef(null),request=useRef(null),timer=useRef(null),generation=useRef(0);
 function release(){stream.current?.getTracks().forEach(t=>t.stop());stream.current=null;clearInterval(timer.current);}
 function stopAll(){generation.current++;cancelled.current=true;request.current?.abort();if(recorder.current?.state==='recording')recorder.current.stop();release();audio.current?.pause();audio.current=null;if(url.current)URL.revokeObjectURL(url.current);url.current=null;setState('idle');setPlaying(false);}
 useEffect(()=>()=>stopAll(),[]);
 useEffect(()=>{if(disabled)stopAll()},[disabled]);
 useEffect(()=>{stopAll()},[session.id,session.current_question.id]);
 async function record(){
  stopAll();cancelled.current=false;const epoch=generation.current;
  try {
   if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw Error('Microphone recording is unavailable in this browser. Please type your answer.');
   const mime=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(t=>MediaRecorder.isTypeSupported(t));
   if(!mime)throw Error('This browser does not support a recording format we can transcribe. Please type.');
   setState('permission');const media=await navigator.mediaDevices.getUserMedia({audio:true});
   if(epoch!==generation.current){media.getTracks().forEach(t=>t.stop());return;}
   stream.current=media;chunks.current=[];recorder.current=new MediaRecorder(media,{mimeType:mime});
   recorder.current.ondataavailable=e=>{if(e.data.size)chunks.current.push(e.data)};
   recorder.current.onerror=()=>{stopAll();onError('Recording was interrupted. Please try again or type.');};
   recorder.current.onstop=async()=>{
    release();if(cancelled.current||epoch!==generation.current)return;
    setState('transcribing');const controller=new AbortController();request.current=controller;
    try {
     const blob=new Blob(chunks.current,{type:mime});chunks.current=[];
     if(blob.size>8*1024*1024)throw Error('Recording too large. Please record a shorter response.');
     const response=await fetch(`/api/sessions/${session.id}/audio/transcriptions`,{method:'POST',headers:{'Content-Type':mime},body:blob,signal:controller.signal});
     const data=await response.json();if(!response.ok)throw Error(data.detail||'Transcription failed.');
     if(epoch===generation.current)onTranscript(data.text);
    }catch(e){if(e.name!=='AbortError'&&epoch===generation.current)onError(e.message)}
    finally{if(epoch===generation.current)setState('idle');}
   };
   recorder.current.start();setSeconds(0);setState('recording');let elapsed=0;
   timer.current=setInterval(()=>{setSeconds(++elapsed);if(elapsed>=90&&recorder.current?.state==='recording')recorder.current.stop()},1000);
  }catch(e){release();if(epoch===generation.current){setState('idle');onError(e.name==='NotAllowedError'?'Microphone permission was denied. You can continue by typing.':e.message)}}
 }
 async function speak(){
  stopAll();const epoch=generation.current;setPlaying(true);const controller=new AbortController();request.current=controller;
  try {
   const t=[...session.turns].reverse().find(t=>t.role==='guide');
   const response=await fetch(`/api/sessions/${session.id}/audio/speech`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({turn_id:t.id}),signal:controller.signal});
   if(!response.ok){const d=await response.json();throw Error(d.detail||'Playback unavailable.')}
   const blob=await response.blob();if(epoch!==generation.current)return;
   url.current=URL.createObjectURL(blob);audio.current=new Audio(url.current);audio.current.onended=()=>stopAll();await audio.current.play();
  }catch(e){if(epoch===generation.current){stopAll();if(e.name!=='AbortError')onError(e.message)}}
 }
 return <div className="voice-controls"><div className="voice-buttons">
  {state==='idle'?<button type="button" className="secondary" disabled={!enabled||disabled} onClick={record}>◉ Speak your response</button>:<><span role="status">{state==='recording'?`Recording · ${seconds}s / 90s`:state==='permission'?'Waiting for microphone…':'Transcribing…'}</span>{state==='recording'&&<button type="button" className="secondary" onClick={()=>recorder.current.stop()}>Stop & transcribe</button>}<button type="button" onClick={stopAll}>Cancel</button></>}
  <button type="button" className="secondary" disabled={!enabled||disabled||state!=='idle'} onClick={playing?stopAll:speak}>{playing?'Stop / mute':'Read aloud'}</button>
 </div><small>{enabled?'Audio is processed by OpenAI. Review the transcript before sending. Playback uses an AI-generated voice.':'Microphone transcription and AI speech become available when the server API key is configured.'}</small></div>
}
