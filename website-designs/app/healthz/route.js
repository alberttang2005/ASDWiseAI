export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export async function GET() {
  try {
    const secret=process.env.ASDWISE_GATEWAY_SECRET;
    if (!secret) throw new Error('not ready');
    const response=await fetch(new URL('/ready',process.env.ASDWISE_API_URL || 'http://127.0.0.1:8001'), {
      headers:{'x-gateway-secret':secret}, cache:'no-store', signal:AbortSignal.timeout(3000)
    });
    return Response.json({ready:response.ok},{status:response.ok?200:503,headers:{'Cache-Control':'no-store'}});
  } catch {return Response.json({ready:false},{status:503,headers:{'Cache-Control':'no-store'}});}
}
