import http from 'node:http';
import {readFile,realpath,stat} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const defaultRoot=fileURLToPath(new URL('../dist/',import.meta.url));
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.woff2':'font/woff2','.json':'application/json','.pdf':'application/pdf','.png':'image/png','.ico':'image/x-icon','.txt':'text/plain; charset=utf-8'};
const within=(root,file)=>file===root||file.startsWith(root+path.sep);

export function deploymentPort(value=process.env.PORT||'5174'){
 const port=Number(value);
 if(!/^\d+$/.test(String(value))||!Number.isInteger(port)||port<1||port>65535)throw new Error('PORT must be an integer from 1 to 65535.');
 return port;
}

export async function createStaticServer({root=defaultRoot,csp=process.env.LAGA_CSP,apiOrigin}={}){
 if(apiOrigin&&!/^http:\/\/127\.0\.0\.1:\d+$/.test(apiOrigin))throw new Error('API upstream must be a loopback HTTP origin.');
 if(csp)http.validateHeaderValue('Content-Security-Policy',csp);
 let publicRoot;
 try{
  publicRoot=await realpath(root);
  for(const entry of ['index.html','api-docs/index.html'])if(!(await stat(path.join(publicRoot,entry))).isFile())throw Error('Invalid build entry.');
 }catch{throw new Error('Frontend build is missing or incomplete. Run npm run build before starting the production server. Keep dist/index.html and dist/api-docs/index.html in the deployment.');}
 return http.createServer(async(req,res)=>{
  const common={'X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin',...(csp?{'Content-Security-Policy':csp}:{})};
  function send(status,body,type='text/plain; charset=utf-8',headers={}){
   const bytes=Buffer.isBuffer(body)?body:Buffer.from(body);
   res.writeHead(status,{...common,'Content-Type':type,'Content-Length':bytes.length,'Cache-Control':'no-store',...headers});
   res.end(req.method==='HEAD'?undefined:bytes);
  }
  try{
   const url=new URL(req.url,'http://localhost');
   const decoded=decodeURIComponent(url.pathname);
   if(decoded.includes('\0'))return send(400,'Invalid request');
   if(apiOrigin&&(decoded==='/api'||decoded.startsWith('/api/'))){
    const upstream=http.request(apiOrigin+req.url,{method:req.method,headers:{...req.headers,host:new URL(apiOrigin).host,'x-forwarded-for':req.socket.remoteAddress,'x-forwarded-proto':'https'}},response=>{
     res.writeHead(response.statusCode,{...common,...response.headers});response.pipe(res);
    });
    upstream.setTimeout(30000,()=>upstream.destroy());
    upstream.on('error',()=>{if(res.headersSent)res.destroy();else send(503,JSON.stringify({error:{code:'BACKEND_UNAVAILABLE',message:'The backend is unavailable. Please try again.',requestId:randomUUID(),fields:{}}}),'application/json')});
    req.on('aborted',()=>upstream.destroy());req.pipe(upstream);return;
   }
   if(decoded==='/api'||decoded.startsWith('/api/'))return send(503,JSON.stringify({error:{code:'BACKEND_NOT_CONNECTED',message:'This server serves the frontend only. Configure a backend API origin or route /api to your backend.',requestId:randomUUID(),fields:{}}}),'application/json');
   if(!['GET','HEAD'].includes(req.method))return send(405,'Method not allowed','text/plain; charset=utf-8',{Allow:'GET, HEAD'});
   if(decoded==='/healthz')return send(200,JSON.stringify({status:'ok',service:'laga-frontend'}),'application/json');
   if(decoded.includes('\\'))return send(403,'Forbidden');
   let file=path.resolve(publicRoot,'.'+decoded);
   if(!within(publicRoot,file))return send(403,'Forbidden');
   if(decoded.split('/').some(segment=>segment.startsWith('.')))return send(404,'Not found');
   try{
    const info=await stat(file);
    if(info.isDirectory())file=path.join(file,'index.html');
    else if(!info.isFile())return send(404,'Not found');
   }catch(error){
    if(!['ENOENT','ENOTDIR'].includes(error.code))throw error;
    // Only application routes fall back to the SPA, never docs or assets.
    if(path.extname(decoded)||/^\/(?:assets|api-docs)(?:\/|$)/.test(decoded))return send(404,'Not found');
    file=path.join(publicRoot,'index.html');
   }
   try{file=await realpath(file)}catch(error){if(['ENOENT','ENOTDIR'].includes(error.code))return send(404,'Not found');throw error}
   if(!within(publicRoot,file))return send(403,'Forbidden');
   const bytes=await readFile(file);
   const cache=path.relative(publicRoot,file).startsWith('assets'+path.sep)?'public, max-age=31536000, immutable':'no-cache';
   send(200,bytes,mime[path.extname(file).toLowerCase()]||'application/octet-stream',{'Cache-Control':cache});
  }catch(error){
   if(error instanceof URIError||error instanceof TypeError)return send(400,'Invalid request');
   if(['ENOENT','ENOTDIR'].includes(error.code))return send(404,'Not found');
   console.error('Frontend request failed:',error.code||error.name);
   send(500,'The frontend could not serve this request.');
  }
 });
}

// Importing this module for smoke tests does not start a listener.
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{
  const port=deploymentPort();
  const server=await createStaticServer();
  server.on('error',error=>{console.error('Frontend startup failed:',error.code||error.message);process.exitCode=1});
  server.listen(port,'0.0.0.0',()=>console.log('Laga frontend listening on 0.0.0.0:'+port));
  let stopping=false;
  const stop=()=>{
   if(stopping)return;stopping=true;
   const deadline=setTimeout(()=>{server.closeAllConnections();process.exit(0)},10000);deadline.unref();
   server.close(()=>{clearTimeout(deadline)});
  };
  process.once('SIGTERM',stop);process.once('SIGINT',stop);
 }catch(error){console.error(error.message);process.exitCode=1}
}
