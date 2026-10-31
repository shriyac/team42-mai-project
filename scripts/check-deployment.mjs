import assert from 'node:assert/strict';
import {readFile,readdir} from 'node:fs/promises';
import {once} from 'node:events';
import {createStaticServer} from './serve.mjs';

const server=await createStaticServer();server.listen(0,'127.0.0.1');await once(server,'listening');
const base='http://127.0.0.1:'+server.address().port;
try{
 for(const route of ['/','/api-docs/']){
  const response=await fetch(base+route);assert.equal(response.status,200);assert.match(response.headers.get('content-type'),/text\/html/);
  const html=await response.text();assert.match(html,route==='/'?/Laga/:/Laga API Explorer/);
  for(const [,asset]of html.matchAll(/(?:src|href)="(\/assets\/[^\"]+)"/g))assert.equal((await fetch(base+asset)).status,200,asset);
 }
 const assets=await readdir(new URL('../dist/assets/',import.meta.url));
 for(const file of assets){
  const response=await fetch(base+'/assets/'+encodeURIComponent(file));assert.equal(response.status,200,file);
  assert.match(response.headers.get('cache-control'),/immutable/);
  if(file.endsWith('.pdf')){assert.equal(response.headers.get('content-type'),'application/pdf');assert.equal((await response.text()).slice(0,5),'%PDF-')}
 }
 for(const method of ['GET','POST','DELETE','OPTIONS'])assert.equal((await fetch(base+'/api/v1/auth/session',{method})).status,503);
 assert.equal((await fetch(base+'/api-docs/not-a-page')).status,404);
 assert.equal((await(await fetch(base+'/healthz')).json()).status,'ok');
 const config=await readFile(new URL('../.replit',import.meta.url),'utf8');assert.ok(!config.startsWith('\ufeff'),'Replit TOML must not have a BOM');
 assert.match(config,/modules\s*=\s*\[[^\]]*"nodejs-22"[^\]]*\]/);assert.match(config,/npm ci --include=dev/);assert.match(config,/externalPort\s*=\s*80/);
 console.log(`Deployment smoke check passed: built app, API Explorer, ${assets.length} assets, PDF, health, API errors and Replit configuration.`);
}finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve))}
