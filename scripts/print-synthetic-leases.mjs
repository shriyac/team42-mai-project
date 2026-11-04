import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';

const directory=fileURLToPath(new URL('../docs/synthetic-leases/',import.meta.url));
const manifestPath=path.join(directory,'manifest.json');
const manifest=JSON.parse(await fs.readFile(manifestPath,'utf8'));
const endpoint=process.env.LAGA_DOCUMENT_BROWSER||'http://127.0.0.1:9224';
let browser;
try{browser=await(await fetch(endpoint+'/json/version')).json()}catch{throw Error('Start Chromium/Edge with local remote debugging on port 9224, or set LAGA_DOCUMENT_BROWSER. See docs/synthetic-leases/README.md.')}
const socket=new WebSocket(browser.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})});
let sequence=0;const jobs=new Map();
socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const job=jobs.get(message.id);jobs.delete(message.id);message.error?job.reject(Error(JSON.stringify(message.error))):job.resolve(message.result)}});
const call=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++sequence;jobs.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}))});
let targetId;
try{
 targetId=(await call('Target.createTarget',{url:'about:blank'})).targetId;
 const sessionId=(await call('Target.attachToTarget',{targetId,flatten:true})).sessionId;
 const send=(method,params={})=>call(method,params,sessionId);
 const run=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value};
 await send('Page.enable');await send('Runtime.enable');
 await send('Emulation.setEmulatedMedia',{media:'print'});
 await send('Emulation.setDeviceMetricsOverride',{width:816,height:1056,deviceScaleFactor:1,mobile:false});
 for(const entry of manifest.documents){
  const url=pathToFileURL(path.join(directory,entry.html)).href;
  await send('Page.navigate',{url});
  let ready=false;
  for(let i=0;i<100;i++){
   ready=await run(`location.href===${JSON.stringify(url)}&&document.readyState==='complete'&&document.querySelectorAll('.page').length===${entry.pages}`);
   if(ready)break;
   await new Promise(resolve=>setTimeout(resolve,50));
  }
  if(!ready)throw Error('Lease HTML did not load: '+entry.html);
  const audit=await run(`(()=>{const pages=[...document.querySelectorAll('.page')];return {pages:pages.length,overflow:pages.flatMap((p,i)=>{const content=p.querySelector('.content'),footer=p.querySelector('footer');return content.getBoundingClientRect().bottom>footer.getBoundingClientRect().top-8||content.scrollWidth>content.clientWidth+1?[i+1]:[]}),text:document.body.innerText}})()`);
  if(audit.overflow.length)throw Error(entry.html+' has overflowing pages: '+audit.overflow.join(','));
  if(!audit.text.includes(entry.tenantName)||!audit.text.includes(entry.documentId.replace('lease-document-','lease-')))throw Error('Wrong lease rendered');
  const result=await send('Page.printToPDF',{printBackground:true,preferCSSPageSize:true,displayHeaderFooter:false,generateTaggedPDF:true,generateDocumentOutline:true});
  const bytes=Buffer.from(result.data,'base64');
  const pages=[...bytes.toString('latin1').matchAll(/\/Type\s*\/Page\b/g)].length;
  if(pages!==entry.pages||bytes.subarray(0,5).toString()!=='%PDF-')throw Error('Invalid page count or PDF signature: '+entry.pdf);
  await fs.writeFile(path.join(directory,entry.pdf),bytes);
  entry.pdfSha256=createHash('sha256').update(bytes).digest('hex');entry.pdfBytes=bytes.length;entry.layoutValidated=true;
  console.log(`${entry.pdf}: ${pages} searchable pages, no overflow`);
 }
 await fs.writeFile(manifestPath,JSON.stringify(manifest,null,2)+'\n');
}finally{if(targetId)await call('Target.closeTarget',{targetId}).catch(()=>{});socket.close()}
