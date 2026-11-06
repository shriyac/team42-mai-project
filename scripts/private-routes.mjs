import path from 'node:path';
import {fileURLToPath} from 'node:url';

const projectRoot=fileURLToPath(new URL('../',import.meta.url)).replace(/\/$/,'');
const privateRoots=new Set(['data','uploads','artifacts','.git','.agents','.local','attached_assets','.streamlit']);

// Run before static lookup and SPA fallback. Repeated decoding also rejects
// encoded separators/dot segments; malformed or excessively encoded paths fail closed.
export function isPrivateRoute(url){
 let pathname=String(url||'/').split('?')[0];
 for(let i=0;i<8;i++){
  try{
   const decoded=decodeURIComponent(pathname);
   if(decoded===pathname)break;
   pathname=decoded;
   if(i===7)return true;
  }catch{return true}
 }
 pathname=pathname.replace(/\\/g,'/');
 if(pathname.includes('\0'))return true;
 for(let candidate of [pathname,path.posix.normalize(pathname)]){
  const filesystem=candidate.startsWith('/@fs/');
  if(filesystem){
   candidate='/'+candidate.slice(5).replace(/^\/+/,'');
   if(candidate.startsWith(projectRoot+'/'))candidate=candidate.slice(projectRoot.length);
   else if(candidate.split('/').some(part=>privateRoots.has(part)))return true;
  }
  const parts=candidate.split('/').filter(Boolean);
  if(privateRoots.has(parts[0]))return true;
  if(parts.some(part=>/^\.env(?:\.|$)/i.test(part)
   || /\.(?:sqlite[^/]*|db(?:-(?:wal|shm|journal))?|pem|crt|key|p12|pfx)$/i.test(part)
   || /bootstrap-login\.json$/i.test(part)
   || /^rag_bindings.*\.json$/i.test(part)
   || part==='documents.json'))return true;
 }
 return false;
}

export function privateRouteGuard(req,res,next){
 if(!isPrivateRoute(req.url))return next();
 res.writeHead(403,{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});
 res.end(req.method==='HEAD'?undefined:'Forbidden');
}

export function privateRoutesPlugin(){
 return {name:'laga-private-routes',
  configureServer(server){server.middlewares.use(privateRouteGuard)},
  configurePreviewServer(server){server.middlewares.use(privateRouteGuard)}};
}
