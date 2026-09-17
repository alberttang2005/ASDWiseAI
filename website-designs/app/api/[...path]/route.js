import { randomUUID } from 'node:crypto';
import { cookies } from 'next/headers';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
const uuid = /^[0-9a-f-]{36}$/i;
async function proxy(request, {params}) {
  const origin = request.headers.get('origin');
  if (!['GET','HEAD'].includes(request.method) && (!origin || origin !== new URL(request.url).origin))
    return Response.json({detail:'Request origin was not accepted.'},{status:403});
  if (!process.env.ASDWISE_GATEWAY_SECRET) return Response.json({detail:'Start the app with npm run pilot to connect the backend.'},{status:503});
  const jar = await cookies(); let owner=jar.get('asdwise_owner')?.value;
  if (!owner || !uuid.test(owner)) owner=randomUUID();
  jar.set('asdwise_owner',owner,{httpOnly:true,sameSite:'strict',secure:new URL(request.url).protocol==='https:',path:'/'});
  const {path} = await params;
  const url = new URL(`/${path.map(encodeURIComponent).join('/')}`,process.env.ASDWISE_API_URL || 'http://127.0.0.1:8001');
  const length=Number(request.headers.get('content-length') || 0);
  if(length>8*1024*1024)return Response.json({detail:'Recording too large.'},{status:413});
  let body;
  if (!['GET','HEAD'].includes(request.method)) {
    const reader=request.body?.getReader();const chunks=[];let total=0;
    if(reader)while(true){const {done,value}=await reader.read();if(done)break;total+=value.length;if(total>8*1024*1024){await reader.cancel();return new Response('Request too large',{status:413});}chunks.push(value);}
    body=Buffer.concat(chunks);
  }
  try {
    const response=await fetch(url,{method:request.method,headers:{'x-owner':owner,'x-gateway-secret':process.env.ASDWISE_GATEWAY_SECRET,'content-type':request.headers.get('content-type')||'application/json'},body,signal:request.signal,cache:'no-store'});
    const headers={'Content-Type':response.headers.get('content-type')||'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'};
    if(response.headers.has('content-disposition'))headers['Content-Disposition']=response.headers.get('content-disposition');
    return new Response(response.body,{status:response.status,headers});
  } catch {return Response.json({detail:'The local API is unavailable. Start npm run pilot and try again.'},{status:503});}
}
export {proxy as GET,proxy as POST,proxy as PATCH,proxy as DELETE};
