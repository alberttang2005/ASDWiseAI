// Process-wide controls deliberately do not trust cookies or forwarded IP headers.
export class Admission {
  constructor({clock = Date.now, requests = 600, creations = 20, concurrent = 32} = {}) {
    Object.assign(this, {clock, requests, creations, concurrent});
    this.started = clock(); this.count = 0; this.created = 0; this.active = 0;
  }
  acquire(creating) {
    if (this.clock() - this.started >= 60000) {
      this.started = this.clock(); this.count = 0; this.created = 0;
    }
    if (this.count >= this.requests || this.active >= this.concurrent || (creating && this.created >= this.creations)) return null;
    this.count++; this.active++; if (creating) this.created++;
    let released = false;
    return () => { if (!released) { released = true; this.active--; } };
  }
}
const key = Symbol.for('asdwise.gateway.admission');
export const admission = globalThis[key] ??= new Admission();

export async function admitted(request, creating, forward) {
  const release = admission.acquire(creating);
  if (!release) return Response.json({detail: 'Too many requests. Please wait a minute.'},
    {status: 429, headers: {'Retry-After': '60', 'Cache-Control': 'no-store'}});
  const controller = new AbortController();
  const signal = AbortSignal.any([request.signal, controller.signal]);
  const timer = setTimeout(() => controller.abort(), 200000);
  let upstream;
  const finish = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); release(); };
  const abort = () => { if (upstream) { upstream.cancel().catch(() => {}); finish(); } };
  signal.addEventListener('abort', abort, {once: true});
  try {
    const response = await forward(signal);
    if (!response.body) { finish(); return response; }
    upstream = response.body.getReader();
    if (signal.aborted) { await upstream.cancel(); finish(); return new Response(null, {status: 504}); }
    const body = new ReadableStream({
      async pull(controller) {
        try {
          const {done, value} = await upstream.read();
          if (done) { finish(); controller.close(); } else controller.enqueue(value);
        } catch (error) { finish(); controller.error(error); }
      },
      async cancel(reason) { try { await upstream.cancel(reason); } finally { finish(); } }
    });
    return new Response(body, {status: response.status, headers: response.headers});
  } catch (error) { finish(); throw error; }
}
