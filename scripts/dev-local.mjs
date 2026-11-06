// Start a bootstrapped Python API and connect Vite without editing .env files.
import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const vite=path.join(path.dirname(fileURLToPath(import.meta.resolve('vite/package.json'))),'bin/vite.js');
const localPython=path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const python=process.env.LAGA_PYTHON||(existsSync(localPython)?localPython:'python');
const port=Number(process.env.LAGA_LOCAL_API_PORT||8001);
if(!/^\d+$/.test(String(process.env.LAGA_LOCAL_API_PORT||8001))||!Number.isInteger(port)||port<1||port>65535)throw Error('LAGA_LOCAL_API_PORT must be an integer from 1 to 65535.');
const uiPort=Number(process.env.LAGA_LOCAL_UI_PORT||process.env.PORT||5174);
if(!/^\d+$/.test(String(process.env.LAGA_LOCAL_UI_PORT||process.env.PORT||5174))||!Number.isInteger(uiPort)||uiPort<1||uiPort>65535)throw Error('LAGA_LOCAL_UI_PORT must be an integer from 1 to 65535.');
if(port===uiPort)throw Error("Public and internal API ports must differ.");
const env={...process.env,PYTHONPATH:[path.join(root,'src'),process.env.PYTHONPATH].filter(Boolean).join(path.delimiter)};
const children=[];let stopping=false;
function stop(code=0){if(stopping)return;stopping=true;for(const child of children)if(child.exitCode===null)child.kill();process.exitCode=code;}
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>stop());
function start(command,args,extra={}){
 const child=spawn(command,args,{cwd:root,env:{...env,...extra},stdio:'inherit',windowsHide:true});children.push(child);
 child.on('error',error=>{console.error(error.message+'; install Python dependencies with python -m pip install -e ".[api]".');stop(1)});
 child.on('exit',code=>{if(!stopping)stop(code||1)});return child;
}
const api=start(python,['-m','laga.api','--host','127.0.0.1','--port',String(port),...(process.env.REPLIT_DEV_DOMAIN?[]:['--insecure-local-cookie'])]);
let ready=false;
for(let i=0;i<150&&!stopping;i++){
 try{const response=await fetch(`http://127.0.0.1:${port}/api/v1/auth/session`,{signal:AbortSignal.timeout(1000)});if(response.ok){ready=true;break}}catch{}
 await new Promise(resolve=>setTimeout(resolve,200));
}
if(!stopping){
 if(!ready){console.error('Local API did not become ready. Check Python dependency installation and the startup output.');stop(1)}
 else{console.log('API ready. Bootstrap sign-in details are in data/backend-bootstrap-login.json beside the default database.');
  start(process.execPath,[vite,'--port',String(uiPort)],{VITE_LAGA_MODE:'api',VITE_LAGA_API_BASE:'/api/v1',LAGA_API_PROXY:`http://127.0.0.1:${port}`});}
}

if(!stopping&&process.argv.includes('--check')){
 let uiReady=false;
 for(let i=0;i<100&&!stopping;i++){
  try{const response=await fetch(`http://127.0.0.1:${uiPort}/src/services/gateway.js`,{signal:AbortSignal.timeout(1000)});const body=await response.text();if(response.ok&&/"VITE_LAGA_MODE":\s*"api"/.test(body)){uiReady=true;break}}catch{}
  await new Promise(resolve=>setTimeout(resolve,200));
 }
 if(uiReady){
  try{
   const base='http://127.0.0.1:'+uiPort;
   const session=await fetch(base+'/api/v1/auth/session');
   if(!session.ok||(await session.json()).data.user!==null)throw Error('Preview API proxy/session check failed');
   if(process.env.LAGA_BOOTSTRAP_PASSWORD){
    const origin=process.env.REPLIT_DEV_DOMAIN?'https://'+process.env.REPLIT_DEV_DOMAIN:base;
    const response=await fetch(base+'/api/v1/auth/login',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:JSON.stringify({email:'alex@alderliving.example',password:process.env.LAGA_BOOTSTRAP_PASSWORD})});
    if(!response.ok)throw Error('Preview login failed: '+response.status);
    const cookie=response.headers.get('set-cookie');
    if(process.env.REPLIT_DEV_DOMAIN&&!cookie.includes('Secure'))throw Error('HTTPS Preview cookie must be Secure');
    const data=(await response.json()).data;
    const headers={Cookie:cookie.split(';')[0],Origin:origin,'Content-Type':'application/json','X-CSRF-Token':data.csrfToken};
    if(!(await fetch(base+'/api/v1/workspace',{headers})).ok)throw Error('Preview workspace failed');
    if(!(await fetch(base+'/api/v1/auth/logout',{method:'POST',headers,body:'{}'})).ok)throw Error('Preview logout failed');
   }
  }catch(error){console.error(error.message);uiReady=false}
 }
 console.log(uiReady?'Local API and UI startup check passed.':'Local UI did not become ready in API mode.');stop(uiReady?0:1);
}
