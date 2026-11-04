import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const root=fileURLToPath(new URL('../',import.meta.url));
const spec=JSON.parse(await fs.readFile(path.join(root,'contracts/openapi.json'),'utf8'));
const stem='Laga-Backend-Integration-Guide-v'+spec.info.version;
const html=path.join(root,'docs',stem+'.html'),pdf=path.join(root,'docs',stem+'.pdf');
const endpoint=process.env.LAGA_DOCUMENT_BROWSER||'http://127.0.0.1:9224';
let browser;try{browser=await(await fetch(endpoint+'/json/version')).json()}catch{throw Error('Start a local Chromium/Edge browser with remote debugging on 9224, or set LAGA_DOCUMENT_BROWSER to its local debugging endpoint. Then rerun this script.')}
const socket=new WebSocket(browser.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})});
let sequence=0;const jobs=new Map();
socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const job=jobs.get(message.id);jobs.delete(message.id);if(message.error)job.reject(Error(JSON.stringify(message.error)));else job.resolve(message.result)}});
const call=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++sequence;jobs.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}))});
let targetId;
try{
 targetId=(await call('Target.createTarget',{url:'about:blank'})).targetId;
 const sessionId=(await call('Target.attachToTarget',{targetId,flatten:true})).sessionId;
 const send=(method,params={})=>call(method,params,sessionId);
 const run=async expression=>{const response=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(response.exceptionDetails)throw Error(JSON.stringify(response.exceptionDetails));return response.result.value};
 await send('Page.enable');await send('Runtime.enable');
 await send('Emulation.setDeviceMetricsOverride',{width:1100,height:1200,deviceScaleFactor:1,mobile:false});
 await send('Emulation.setEmulatedMedia',{media:'print'});
 await send('Page.navigate',{url:pathToFileURL(html).href});
 const deadline=Date.now()+45000;let ready=false;
 while(Date.now()<deadline){const state=await run('({ready:window.bookReady,error:window.bookError})');if(state.error)throw Error(state.error);if(state.ready){ready=true;break}await new Promise(resolve=>setTimeout(resolve,150))}
 if(!ready)throw Error('Document did not finish pagination.');
 const layout=await run('window.bookResult');
 if(layout.overflows.length)throw Error('Document contains overflowing pages.');
 const audit=await run(`(()=>{const pages=[...document.querySelectorAll('.page')];const headings=pages.map((p,i)=>({page:i+1,title:p.querySelector('h1')?.textContent||'Cover'}));const bad=[...document.querySelectorAll('a[href^="#"]')].filter(a=>!document.getElementById(a.hash.slice(1))).map(a=>a.hash);const horizontal=pages.map((p,i)=>({page:i+1,width:p.clientWidth,scroll:p.scrollWidth})).filter(p=>p.scroll>p.width+1);return {headings,brokenInternalLinks:bad,horizontalOverflow:horizontal,bodyText:document.body.innerText}})()`);
 if(audit.brokenInternalLinks.length||audit.horizontalOverflow.length)throw Error('Broken links or horizontal overflow: '+JSON.stringify(audit));
 if(audit.bodyText.includes('<table>')||audit.bodyText.includes('@@HTMLBLOCK'))throw Error('Unrendered markup in document.');
 // Capture representative pages for local visual review before sharing.
 const screenshotDirectory=path.join(root,'data','document-review');await fs.mkdir(screenshotDirectory,{recursive:true});
 for(const index of [0,1,2,Math.floor(layout.pageCount/2),layout.pageCount-2]){
  const rect=await run(`(()=>{const p=document.querySelectorAll('.page')[${index}];const r=p.getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}})()`);
  const image=await send('Page.captureScreenshot',{format:'png',clip:rect,captureBeyondViewport:true});
  await fs.writeFile(path.join(screenshotDirectory,'page-'+String(index+1).padStart(2,'0')+'.png'),Buffer.from(image.data,'base64'));
 }
 const printed=await send('Page.printToPDF',{printBackground:true,preferCSSPageSize:true,displayHeaderFooter:false,marginTop:0,marginBottom:0,marginLeft:0,marginRight:0,generateTaggedPDF:true,generateDocumentOutline:true});
 const bytes=Buffer.from(printed.data,'base64');await fs.writeFile(pdf,bytes);
 const actualPages=[...bytes.toString('latin1').matchAll(/\/Type\s*\/Page\b/g)].length;
 if(actualPages!==layout.pageCount)throw Error(`Expected ${layout.pageCount} pages, PDF has ${actualPages}.`);
 if(!bytes.subarray(0,5).equals(Buffer.from('%PDF-')))throw Error('Invalid PDF signature.');
 const manifestFile=path.join(root,'docs/integration-guide-manifest.json');const manifest=JSON.parse(await fs.readFile(manifestFile,'utf8'));
 manifest.pdf={file:path.relative(root,pdf).replaceAll('\\','/'),pages:actualPages,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),layoutValidated:true,internalLinksValidated:true,tagged:bytes.includes(Buffer.from('/StructTreeRoot')),outline:bytes.includes(Buffer.from('/Outlines')),pageHeadings:audit.headings};
 await fs.writeFile(manifestFile,JSON.stringify(manifest,null,2)+'\n');
 console.log(JSON.stringify({pdf,pages:actualPages,bytes:bytes.length,tagged:manifest.pdf.tagged,outline:manifest.pdf.outline,layoutOverflows:0,brokenInternalLinks:0,sha256:manifest.pdf.sha256}));
}finally{if(targetId)await call('Target.closeTarget',{targetId}).catch(()=>{});socket.close()}
