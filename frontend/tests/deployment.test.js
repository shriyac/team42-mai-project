import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {once} from 'node:events';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {createStaticServer,deploymentPort} from '../../scripts/serve.mjs';

async function fixture(t){
 const base=await mkdtemp(path.join(tmpdir(),'laga-deployment-'));
 t.after(async()=>{assert.ok(path.basename(base).startsWith('laga-deployment-'));await rm(base,{recursive:true,force:true})});
 const root=path.join(base,'dist');await mkdir(path.join(root,'assets'),{recursive:true});await mkdir(path.join(root,'api-docs'));
 for(const [name,body]of Object.entries({'index.html':'<html>Laga app</html>','api-docs/index.html':'<html>Laga API Explorer</html>','assets/app-hash.js':'console.log("Laga")','assets/guide-hash.pdf':'%PDF-fixture','.env':'private fixture'}))await writeFile(path.join(root,name),body);
 const server=await createStaticServer({root});server.listen(0,'127.0.0.1');await once(server,'listening');
 t.after(()=>new Promise(resolve=>{server.closeAllConnections();server.close(resolve)}));
 const baseUrl='http://127.0.0.1:'+server.address().port;
 return {base,root,server,baseUrl};
}

test('deployment fails clearly for invalid ports and missing build output',async()=>{
 assert.equal(deploymentPort('5174'),5174);assert.equal(deploymentPort('8080'),8080);
 for(const input of ['0','65536','abc','5174.5','-1',''])assert.throws(()=>deploymentPort(input),/PORT/);
 await assert.rejects(createStaticServer({root:path.join(tmpdir(),'laga-build-does-not-exist')}),/npm run build/);
});

test('production server serves app, API docs, PDFs, health and HEAD with correct caching',async t=>{
 const {baseUrl}=await fixture(t);
 assert.match(await(await fetch(baseUrl+'/')).text(),/Laga app/);
 for(const endpoint of ['/api-docs','/api-docs/'])assert.match(await(await fetch(baseUrl+endpoint)).text(),/API Explorer/);
 const asset=await fetch(baseUrl+'/assets/app-hash.js');assert.match(asset.headers.get('cache-control'),/immutable/);assert.match(asset.headers.get('content-type'),/javascript/);
 const head=await fetch(baseUrl+'/assets/app-hash.js',{method:'HEAD'});assert.equal(await head.text(),'');assert.equal(head.headers.get('content-length'),asset.headers.get('content-length'));
 const pdf=await fetch(baseUrl+'/assets/guide-hash.pdf');assert.equal(pdf.headers.get('content-type'),'application/pdf');assert.match(await pdf.text(),/^%PDF/);
 const home=await fetch(baseUrl+'/');assert.equal(home.headers.get('cache-control'),'no-cache');assert.equal(home.headers.get('x-content-type-options'),'nosniff');
 assert.deepEqual(await(await fetch(baseUrl+'/healthz')).json(),{status:'ok',service:'laga-frontend'});
 assert.match(await(await fetch(baseUrl+'/some/app/route')).text(),/Laga app/);
 for(const url of ['/assets/missing.js','/assets/missing','/api-docs/missing','/.env'])assert.equal((await fetch(baseUrl+url)).status,404);
});

test('unconnected API reads and mutations return safe JSON 503, never the SPA or 405',async t=>{
 const {baseUrl}=await fixture(t);
 for(const method of ['GET','POST','DELETE','OPTIONS']){
  const response=await fetch(baseUrl+'/api/v1/policies',{method});assert.equal(response.status,503);
  assert.equal(response.headers.get('cache-control'),'no-store');const body=await response.json();assert.equal(body.error.code,'BACKEND_NOT_CONNECTED');assert.ok(body.error.requestId);
 }
 assert.equal((await fetch(baseUrl+'/api')).status,503);
 const mutation=await fetch(baseUrl+'/',{method:'POST'});assert.equal(mutation.status,405);assert.equal(mutation.headers.get('allow'),'GET, HEAD');
});

test('static paths cannot escape dist through encoded traversal or symlinks',async t=>{
 const {baseUrl,base,root}=await fixture(t);
 const request=pathname=>new Promise((resolve,reject)=>{http.get(baseUrl+pathname,response=>{response.resume();resolve(response.statusCode)}).on('error',reject)});
 assert.equal(await request('/%2e%2e%2fprivate.txt'),403);
 assert.equal(await request('/%5c..%5cprivate.txt'),403);
 assert.equal(await request('/bad%ZZ'),400);
 assert.equal(await request('/%00'),400);
 const outside=path.join(base,'private');await mkdir(outside);await writeFile(path.join(outside,'private.txt'),'private fixture');
 try{await symlink(outside,path.join(root,'escape'),process.platform==='win32'?'junction':'dir')}
 catch(error){if(['EPERM','EACCES','ENOSYS'].includes(error.code)){t.diagnostic('Symlink fixture unavailable on this host.');return}throw error}
 assert.equal(await request('/escape/private.txt'),403);
});

test('production CLI honors PORT and serves dist relative to the script from another working directory',async t=>{
 const {base,server,baseUrl}=await fixture(t),port=server.address().port;
 await new Promise(resolve=>server.close(resolve));
 await mkdir(path.join(base,'scripts'));
 const script=path.join(base,'scripts','serve.mjs');
 await writeFile(script,await readFile(new URL('../../scripts/serve.mjs',import.meta.url)));
 const child=spawn(process.execPath,[script],{cwd:tmpdir(),env:{...process.env,PORT:String(port)},stdio:['ignore','pipe','pipe']});
 let output='';child.stdout.on('data',chunk=>output+=chunk);child.stderr.on('data',chunk=>output+=chunk);
 t.after(async()=>{if(child.exitCode===null&&!child.signalCode){child.kill();await once(child,'exit')}});
 const deadline=Date.now()+5000;let response;
 while(Date.now()<deadline){
  if(child.exitCode!==null)throw Error('CLI exited before listening: '+output);
  try{response=await fetch(baseUrl+'/healthz');break}catch{await new Promise(resolve=>setTimeout(resolve,25))}
 }
 assert.ok(response,'CLI did not start: '+output);
 assert.equal(response.status,200);assert.equal((await response.json()).service,'laga-frontend');
 assert.match(output,new RegExp('0\\.0\\.0\\.0:'+port));
 assert.match(await(await fetch(baseUrl+'/')).text(),/Laga app/);
});

test('production proxy preserves login cookies, origin, CSRF and multipart bytes',async t=>{
 const {root}=await fixture(t);
 const upstream=http.createServer((req,res)=>{let body=[];req.on('data',part=>body.push(part));req.on('end',()=>{res.writeHead(201,{'Content-Type':'application/json','Set-Cookie':'session=test; HttpOnly; Secure; Path=/api/v1'});res.end(JSON.stringify({url:req.url,method:req.method,origin:req.headers.origin,csrf:req.headers['x-csrf-token'],cookie:req.headers.cookie,forwarded:req.headers['x-forwarded-for'],body:Buffer.concat(body).toString()}))})});
 upstream.listen(0,'127.0.0.1');await once(upstream,'listening');
 t.after(()=>new Promise(resolve=>{upstream.closeAllConnections();upstream.close(resolve)}));
 const server=await createStaticServer({root,apiOrigin:'http://127.0.0.1:'+upstream.address().port});server.listen(0,'127.0.0.1');await once(server,'listening');
 t.after(()=>new Promise(resolve=>{server.closeAllConnections();server.close(resolve)}));
 const base='http://127.0.0.1:'+server.address().port;
 const response=await fetch(base+'/api/v1/policies?test=1',{method:'POST',headers:{Origin:'https://demo.replit.app','X-Forwarded-For':'203.0.113.99','X-CSRF-Token':'csrf-test',Cookie:'session=input','Content-Type':'multipart/form-data; boundary=example'},body:'--example\r\nPDF bytes\r\n--example--'});
 assert.equal(response.status,201);assert.match(response.headers.get('set-cookie'),/HttpOnly; Secure/);
 assert.deepEqual(await response.json(),{url:'/api/v1/policies?test=1',method:'POST',origin:'https://demo.replit.app',csrf:'csrf-test',cookie:'session=input',forwarded:'127.0.0.1',body:'--example\r\nPDF bytes\r\n--example--'});
 assert.match(await(await fetch(base+'/api-docs/')).text(),/API Explorer/);
 await new Promise(resolve=>{upstream.closeAllConnections();upstream.close(resolve)});
 assert.equal((await fetch(base+'/api/v1/auth/session')).status,503);
 await assert.rejects(createStaticServer({root,apiOrigin:'https://untrusted.example'}),/loopback/);
});
