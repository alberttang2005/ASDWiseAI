import test from 'node:test';
import assert from 'node:assert/strict';
import {Admission, admission, admitted} from '../app/api/admission.mjs';
import {publicOrigin} from '../app/api/origin.mjs';

test('HTTPS origin behind a proxy comes from server configuration', () => {
  const previous=process.env.ASDWISE_PUBLIC_ORIGIN;
  try {
    process.env.ASDWISE_PUBLIC_ORIGIN='https://asdwiseai.org';
    const request=new Request('http://127.0.0.1:3000/api/sessions',{headers:{'x-forwarded-host':'attacker.example','x-forwarded-proto':'http'}});
    assert.equal(publicOrigin(request),'https://asdwiseai.org');
    delete process.env.ASDWISE_PUBLIC_ORIGIN;
    assert.equal(publicOrigin(request),'http://127.0.0.1:3000');
  } finally {
    if(previous===undefined)delete process.env.ASDWISE_PUBLIC_ORIGIN;
    else process.env.ASDWISE_PUBLIC_ORIGIN=previous;
  }
});

test('global request and creation allowances persist when connections finish', () => {
  let now=0;
  const limits=new Admission({clock:()=>now,requests:3,creations:1});
  limits.acquire(true)();
  assert.equal(limits.acquire(true),null);
  limits.acquire(false)();limits.acquire(false)();
  assert.equal(limits.acquire(false),null);
  now=60000;assert.ok(limits.acquire(true));
});
test('concurrency stays bounded and release is idempotent', () => {
  const limits=new Admission({concurrent:1});
  const release=limits.acquire(false);
  assert.equal(limits.acquire(false),null);
  release();release();assert.equal(limits.active,0);
  assert.ok(limits.acquire(false));
});
test('completed and cancelled response streams release admission', async () => {
  const request=new Request('http://localhost/api/health');
  let response=await admitted(request,false,async()=>new Response('ok'));
  assert.equal(admission.active,1);
  assert.equal(await response.text(),'ok');assert.equal(admission.active,0);
  response=await admitted(request,false,async()=>new Response(new ReadableStream()));
  assert.equal(admission.active,1);
  await response.body.cancel();assert.equal(admission.active,0);
});
test('upstream errors release admission', async () => {
  await assert.rejects(admitted(new Request('http://localhost/api/health'),false,async()=>{throw Error('offline');}));
  assert.equal(admission.active,0);
});
test('client disconnect cancels streaming work and releases admission', async () => {
  const controller=new AbortController();let cancelled=false;
  await admitted(new Request('http://localhost/api/events',{signal:controller.signal}),false,
    async()=>new Response(new ReadableStream({cancel(){cancelled=true;}})));
  controller.abort();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(cancelled,true);assert.equal(admission.active,0);
});
