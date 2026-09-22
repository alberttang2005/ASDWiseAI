import {test} from 'node:test';
import assert from 'node:assert/strict';
import {sessionFetch, clearSession} from '../app/session-client.mjs';

test('state travels in request bodies and clearing removes it', async()=>{
 const previous=globalThis.fetch;const bodies=[];
 try {
  clearSession();globalThis.fetch=async(url,options)=>{assert.equal(url,'/api/index');bodies.push(JSON.parse(options.body));return Response.json({data:{ok:true},state:'signed-test-state'});};
  await sessionFetch('/sessions',{method:'POST',body:{name:'Fictional'}});
  await sessionFetch('/sessions/test');
  assert.equal(bodies[0].state,null);assert.equal(bodies[1].state,'signed-test-state');
  clearSession();await sessionFetch('/health');assert.equal(bodies[2].state,null);
 }finally{globalThis.fetch=previous;clearSession();}
});
test('late response cannot resurrect a cleared session',async()=>{
 const previous=globalThis.fetch;let resolve;
 try{
  clearSession();globalThis.fetch=async()=>Response.json({data:{},state:'first'});await sessionFetch('/sessions',{method:'POST'});
  globalThis.fetch=()=>new Promise(r=>{resolve=r});const pending=sessionFetch('/sessions/test');clearSession();resolve(Response.json({data:{},state:'old'}));await pending;
  globalThis.fetch=async(url,o)=>{assert.equal(JSON.parse(o.body).state,null);return Response.json({data:{}});};await sessionFetch('/health');
 }finally{globalThis.fetch=previous;clearSession();}
});
