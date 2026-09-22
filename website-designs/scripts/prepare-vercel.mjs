// Build an allowlisted source bundle; never upload research data or local secrets.
import {cp, mkdir, rm, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const web = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.dirname(web);
const output = path.join(root, '.vercel-source');
await rm(output, {recursive:true, force:true});
await mkdir(path.join(output, 'backend', 'web'), {recursive:true});
for (const name of ['app','public','api','package.json','package-lock.json','next.config.mjs','vercel.json']) await cp(path.join(web,name),path.join(output,name),{recursive:true});
// The old local gateway is not part of the Vercel application.
await rm(path.join(output,'app','api'),{recursive:true,force:true});
await rm(path.join(output,'app','healthz'),{recursive:true,force:true});
for (const name of ['__init__.py','api.py','domain.py','store.py','security.py','providers.py','reports.py','reference.json','serverless.py']) await cp(path.join(root,'src','web',name),path.join(output,'backend','web',name));
await mkdir(path.join(output,'backend','utils'),{recursive:true});
for(const name of ['__init__.py','mchat_scorer.py']) await cp(path.join(root,'src','utils',name),path.join(output,'backend','utils',name));
await mkdir(path.join(output,'backend','data'),{recursive:true});
await cp(path.join(root,'src','data','mchat_questions.json'),path.join(output,'backend','data','mchat_questions.json'));
await cp(path.join(root,'src','web','requirements.lock.txt'),path.join(output,'requirements.txt'));
await writeFile(path.join(output,'.vercelignore'),'node_modules\n.next\n.env*\n');
console.log(output);
