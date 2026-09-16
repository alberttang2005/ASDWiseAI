import {spawn} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const web=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const repo=path.dirname(web);
const env={...process.env,ASDWISE_GATEWAY_SECRET:randomBytes(32).toString('hex'),PYTHONPATH:path.join(repo,'src'),PYTHONUNBUFFERED:'1'};
const python=process.env.ASDWISE_PYTHON||path.join(repo,'.venv','bin','python');
const api=spawn(python,['-m','web.run'],{cwd:repo,env,stdio:'inherit'});
const next=spawn(process.execPath,[path.join(web,'node_modules/next/dist/bin/next'),process.env.ASDWISE_PRODUCTION==='1'?'start':'dev','--hostname','127.0.0.1','--port',process.env.PORT||'3000'],{cwd:web,env,stdio:'inherit'});
let ending=false;
function close(code=0){if(ending)return;ending=true;api.kill('SIGTERM');next.kill('SIGTERM');setTimeout(()=>process.exit(code),300);}
for(const child of [api,next]){child.on('error',()=>{console.error('Could not start the pilot. Check the Python environment and README.');close(1)});child.on('exit',code=>close(code||0));}
process.on('SIGINT',()=>close());process.on('SIGTERM',()=>close());
