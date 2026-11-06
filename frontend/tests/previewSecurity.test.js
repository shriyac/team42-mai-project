import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import {createServer} from 'vite';
import {createStaticServer} from '../../scripts/serve.mjs';
import {mkdtemp,writeFile,rm,mkdir,symlink} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const root=fileURLToPath(new URL('../../',import.meta.url)).replace(/\/$/,'');
export const privatePaths=[
 '/data/backend.sqlite3','/data/backend-bootstrap-login.json',
 '/data/demo-phase7d/backend.sqlite3','/data/demo-phase7d/backend-bootstrap-login.json',
 '/data/retired-phase7d/backend.sqlite3','/data/retired-phase7d/backend-bootstrap-login.json',
 '/data/retired-phase7d/verification.json','/data/missing',
 '/.env','/.env.local','/secret.pem','/server.key','/backup.db','/backup.sqlite3-wal',
 '/backend-bootstrap-login.json','/rag_bindings.json','/rag_bindings.pending.json',
 '/documents.json','/artifacts/lease_rag_local/active.json',
 '/.git/config','/.agents/memory/MEMORY.md','/.local/private',
 '/uploads/private.pdf','/attached_assets/private.txt','/.streamlit/secrets.toml',
];
export function privateRouteMatrix(){
 return privatePaths.flatMap(file=>[
  file,file+'?raw',file+'?url',
  '/@fs/'+root+file,'/@fs'+root+file,
  '/%'+file.charCodeAt(1).toString(16)+file.slice(2),
  '/src/..'+file,'/src/%2e%2e'+file,'/src/%252e%252e'+file,
  '/src/..%2f'+file.slice(1),'/src/%2e%2e%5c'+file.slice(1),
  '/@fs/'+encodeURIComponent(root+file),
 ]);
}
function request(server,url,method='GET'){
 return new Promise((resolve,reject)=>{
  const req=http.request({host:'127.0.0.1',port:server.address().port,path:url,method},res=>{
   res.resume();res.on('end',()=>resolve(res.statusCode));
  });req.on('error',reject);req.end();
 });
}

test('preview rejects ordinary, filesystem, encoded and traversal private routes before SPA fallback',async t=>{
 const server=await createServer({server:{host:'127.0.0.1',port:0,open:false},logLevel:'silent'});
 await server.listen();t.after(()=>server.close());
 for(const route of privateRouteMatrix()){
  assert.equal(await request(server.httpServer,route),403,route);
 }
 assert.equal(await request(server.httpServer,'/data/backend.sqlite3','HEAD'),403);
 for(const route of ['/','/tenant','/ask','/src/data/fixtures.js','/api-docs/']){
  assert.equal(await request(server.httpServer,route),200,route);
 }
});

test('production static server rejects private files before lookup, fallback and symlink resolution',async t=>{
 const dir=await mkdtemp(path.join(os.tmpdir(),'laga-private-routes-'));
 t.after(()=>rm(dir,{recursive:true,force:true}));
 await mkdir(path.join(dir,'api-docs'));
 await writeFile(path.join(dir,'index.html'),'<!doctype html><title>Test app</title>');
 await writeFile(path.join(dir,'api-docs/index.html'),'docs');
 // Even accidentally packaged private files must never be served.
 await mkdir(path.join(dir,'data'));
 await writeFile(path.join(dir,'data/backend.sqlite3'),'test-canary');
 await writeFile(path.join(dir,'backend-bootstrap-login.json'),'test-canary');
 await writeFile(path.join(dir,'rag_bindings.json'),'test-canary');
 await symlink(root+'/data',path.join(dir,'linked-private'));
 const server=await createStaticServer({root:dir});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 t.after(()=>new Promise(resolve=>server.close(resolve)));
 for(const route of privateRouteMatrix())assert.equal(await request(server,route),403,route);
 assert.equal(await request(server,'/linked-private/backend-bootstrap-login.json'),403);
 for(const route of ['/','/tenant','/ask','/api-docs/','/healthz']){
  assert.equal(await request(server,route),200,route);
 }
});
