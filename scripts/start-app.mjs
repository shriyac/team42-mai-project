// Production: one public listener; Python stays on loopback.
import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createStaticServer,deploymentPort} from './serve.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const pythonLocal=path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const python=process.env.LAGA_PYTHON||(existsSync(pythonLocal)?pythonLocal:'python');
const publicPort=deploymentPort();
const apiPort=deploymentPort(process.env.LAGA_LOCAL_API_PORT||'8001');
if(apiPort===publicPort)throw Error('Public and internal API ports must differ.');
const origin='http://127.0.0.1:'+apiPort;
const server=await createStaticServer({apiOrigin:origin});
const api=spawn(python,['-m','laga.api','--host','127.0.0.1','--port',String(apiPort)],{cwd:root,windowsHide:true,stdio:'inherit',env:{...process.env,PYTHONPATH:[path.join(root,'src'),process.env.PYTHONPATH].filter(Boolean).join(path.delimiter)}});
let stopping=false;
function stop(code=0){if(stopping)return;stopping=true;process.exitCode=code;server.closeAllConnections();server.close();api.kill();}
process.once('SIGTERM',()=>stop());process.once('SIGINT',()=>stop());
api.on('error',error=>{console.error('Python API could not start:',error.message);stop(1)});
api.on('exit',code=>{if(!stopping)stop(code||1)});
server.on('error',error=>{console.error('Application listener failed:',error.code);stop(1)});
let ready=false;
for(let attempt=0;attempt<150&&!stopping;attempt++){
 try{const response=await fetch(origin+'/api/v1/auth/session',{signal:AbortSignal.timeout(1000)});if(response.ok){ready=true;break}}catch{}
 await new Promise(resolve=>setTimeout(resolve,200));
}
if(!stopping){if(!ready){console.error('Python API readiness check failed.');stop(1)}else server.listen(publicPort,'0.0.0.0',async()=>{
 console.log('Laga application listening on port '+publicPort);
 if(process.argv.includes('--check')){
  try{
   const base='http://127.0.0.1:'+publicPort;
   for(const route of ['/','/api-docs/','/healthz','/api/v1/auth/session']){
    const response=await fetch(base+route);if(!response.ok)throw Error('Readiness route failed: '+route);
    if(route.endsWith('/auth/session')&&(await response.json()).data.user!==null)throw Error('Unexpected initial session');
   }
   if(process.env.LAGA_BOOTSTRAP_PASSWORD){
    const publishedOrigin=process.env.LAGA_ALLOWED_ORIGINS?.split(',')[0]||'https://'+process.env.REPLIT_DOMAINS?.split(',')[0];
    for(const [email,role] of [['alex@alderliving.example','landlord'],['maya@example.test','tenant']]){
    const login=await fetch(base+'/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json',Origin:publishedOrigin},body:JSON.stringify({email,password:process.env.LAGA_BOOTSTRAP_PASSWORD})});
    if(!login.ok)throw Error('Published-origin login failed: '+login.status);
    const cookie=login.headers.get('set-cookie');if(!cookie?.includes('Secure')||!cookie.includes('HttpOnly'))throw Error('Production cookie protection missing');
    const session=(await login.json()).data;if(session.user.role!==role)throw Error('Account role mismatch');
    const csrf=session.csrfToken;
    const headers={Cookie:cookie.split(';')[0],Origin:publishedOrigin,'X-CSRF-Token':csrf,'Content-Type':'application/json'};
    const workspace=await fetch(base+'/api/v1/workspace',{headers});if(!workspace.ok)throw Error('Authenticated workspace failed');
    if(role==='tenant'&&(await workspace.json()).data.leases.some(lease=>lease.tenantId!==session.user.id))throw Error('Tenant scope mismatch');
    const restored=await(await fetch(base+'/api/v1/auth/session',{headers})).json();if(restored.data.user.id!==session.user.id)throw Error('Session reload failed');
    const noCsrf={Cookie:headers.Cookie,Origin:publishedOrigin,'Content-Type':'application/json'};
    if((await fetch(base+'/api/v1/auth/logout',{method:'POST',headers:noCsrf,body:'{}'})).status!==403)throw Error('Missing CSRF accepted');
    if((await fetch(base+'/api/v1/auth/logout',{method:'POST',headers:{...headers,Origin:'https://untrusted.example'},body:'{}'})).status!==403)throw Error('Foreign origin accepted');
    if(!(await fetch(base+'/api/v1/auth/logout',{method:'POST',headers,body:'{}'})).ok)throw Error('Logout failed');
    if((await fetch(base+'/api/v1/workspace',{headers})).status!==401)throw Error('Session survived logout');
    }
   }
   console.log('Production frontend and Python API startup check passed.');stop();
  }catch(error){console.error(error.message);stop(1)}
 }
});}
