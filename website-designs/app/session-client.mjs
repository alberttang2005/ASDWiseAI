// Only JavaScript memory: never localStorage, sessionStorage, cookies, or URLs.
let snapshot = null;
export function clearSession() { snapshot = null; }
export async function sessionFetch(path, options = {}) {
  const {method = 'GET', body, signal, headers = {}} = options;
  const envelope = {path, method, state: snapshot};
  if (body instanceof Blob) {
    const bytes = new Uint8Array(await body.arrayBuffer());
    let binary = '';
    for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
    envelope.audio = btoa(binary);
    envelope.content_type = headers['Content-Type'] || body.type;
  } else if (body !== undefined) envelope.body = typeof body === 'string' ? JSON.parse(body) : body;
  const response = await fetch('/api/index', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(envelope), signal, cache:'no-store'});
  const result = await response.json();
  if (response.ok && 'state' in result && path !== '/health' && snapshot === envelope.state) snapshot = result.state;
  if (response.status === 410) clearSession();
  if (result.binary !== undefined) {
    const bytes = Uint8Array.from(atob(result.binary), c => c.charCodeAt(0));
    return new Response(bytes, {status:response.status, headers:{'Content-Type':result.content_type}});
  }
  return new Response(JSON.stringify(result.data ?? result), {status:response.status, headers:{'Content-Type':'application/json'}});
}
