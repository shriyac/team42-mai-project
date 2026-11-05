import test from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {createServer} from 'vite';
import {mkdtemp,writeFile,rm,stat} from 'node:fs/promises';

test('preview denies private runtime files while serving the UI and fictional fixtures',async t=>{
 const server=await createServer({server:{host:'127.0.0.1',port:0,open:false},logLevel:'silent'});
 await server.listen();
 t.after(()=>server.close());
 const base=`http://127.0.0.1:${server.httpServer.address().port}`;
 const root=fileURLToPath(new URL('../../',import.meta.url));
 const privateDir=await mkdtemp(root+'data/preview-security-');
 t.after(()=>rm(privateDir,{recursive:true,force:true}));
 await writeFile(privateDir+'/credentials.json','{"password":"fake-test-only"}');
 assert.equal((await fetch(base+'/@fs/'+privateDir+'/credentials.json')).status,403);
 assert.ok(server.config.server.fs.deny.includes('.env'));
 for(const relative of ['data/backend.sqlite3','data/backend-bootstrap-login.json',
  'rag_bindings.pending.json','documents.json','.env']){
  for(const prefix of ['/@fs/','/@fs']){
   const response=await fetch(base+prefix+root+relative);
   if(await stat(root+relative).then(()=>true,()=>false)){
    assert.equal(response.status,403,`Private path must be denied: ${relative}`);
   }else{
    assert.ok(response.status===403||response.headers.get('content-type')?.includes('text/html'));
   }
  }
 }
 assert.equal((await fetch(base+'/')).status,200);
 assert.equal((await fetch(base+'/src/data/fixtures.js')).status,200);
});
