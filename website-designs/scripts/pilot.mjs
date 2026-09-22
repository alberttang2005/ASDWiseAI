import {spawn} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const web=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const repo=path.dirname(web);
const host=process.env.ASDWISE_BIND_HOST||'127.0.0.1';
if(host!=='127.0.0.1') {
  let origin;
  try {origin=new URL(process.env.ASDWISE_PUBLIC_ORIGIN);} catch {}
  if(process.env.ASDWISE_PRODUCTION!=='1' || !origin || origin.protocol!=='https:' || origin.origin!==process.env.ASDWISE_PUBLIC_ORIGIN) {
    console.error('Public hosting requires a production build and ASDWISE_PUBLIC_ORIGIN set to the exact HTTPS origin.');
    process.exit(1);
  }
}
const env={...process.env,ASDWISE_GATEWAY_SECRET:randomBytes(32).toString('hex'),ASDWISE_SESSION_SECRET:process.env.ASDWISE_SESSION_SECRET||randomBytes(32).toString('hex'),ASDWISE_PUBLIC_ORIGIN:process.env.ASDWISE_PUBLIC_ORIGIN||'http://localhost:'+(process.env.PORT||'3000'),PYTHONPATH:path.join(repo,'src'),PYTHONUNBUFFERED:'1'};
const python=process.env.ASDWISE_PYTHON||path.join(repo,'.venv','bin','python');
const api=spawn(python,['-m','web.run'],{cwd:repo,env,stdio:'inherit'});
const next=spawn(process.execPath,[path.join(web,'node_modules/next/dist/bin/next'),process.env.ASDWISE_PRODUCTION==='1'?'start':'dev','--hostname',host,'--port',process.env.PORT||'3000'],{cwd:web,env,stdio:'inherit'});
let ending=false;
function close(code=0){if(ending)return;ending=true;api.kill('SIGTERM');next.kill('SIGTERM');setTimeout(()=>process.exit(code),300);}
for(const child of [api,next]){child.on('error',()=>{console.error('Could not start the pilot. Check the Python environment and README.');close(1)});child.on('exit',code=>close(code||0));}
process.on('SIGINT',()=>close());process.on('SIGTERM',()=>close());
