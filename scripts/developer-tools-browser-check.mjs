import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const targets=await(await fetch('http://127.0.0.1:9224/json')).json();
const target=targets.find(t=>t.type==='page'&&t.url.includes('5174'));
assert.ok(target,'Open the app in a browser with remote debugging on port 9224.');
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}));
let id=0;const pending=new Map(),errors=[];
socket.addEventListener('message',event=>{const m=JSON.parse(event.data);if(m.id){const job=pending.get(m.id);pending.delete(m.id);m.error?job.reject(m.error):job.resolve(m.result)}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails)});
const call=(method,params={})=>new Promise((resolve,reject)=>{const next=++id;pending.set(next,{resolve,reject});socket.send(JSON.stringify({id:next,method,params}))});
const run=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value};
const wait=async expression=>{const end=Date.now()+7000;while(Date.now()<end){if(await run(expression))return;await new Promise(r=>setTimeout(r,100))}throw Error('Timed out: '+expression)};
const click=async text=>{await wait(`[...document.querySelectorAll('button')].some(b=>!b.disabled&&b.textContent.trim().startsWith(${JSON.stringify(text)}))`);await run(`(()=>{const button=[...document.querySelectorAll('button')].find(b=>b.textContent.trim().startsWith(${JSON.stringify(text)}));button.focus();button.click()})()`)};
const close=()=>run(`document.querySelector('dialog [aria-label="Close dialog"]').click()`);
const screenshot=async name=>{await new Promise(resolve=>setTimeout(resolve,350));const shot=await call('Page.captureScreenshot',{format:'png'});await fs.writeFile('data/browser-check/'+name+'.png',Buffer.from(shot.data,'base64'))};

try{
 await call('Runtime.enable');await call('Page.enable');await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});await call('Page.navigate',{url:'http://localhost:5174/'});await wait(`!!document.querySelector('[role=switch]')`);
 await run('document.fonts.ready.then(()=>true)');assert.equal(await run(`document.querySelector('[role=switch]').getAttribute('aria-checked')`),'false');assert.equal(await run(`!!document.querySelector('.developer-docs-link:not([hidden])')`),false);
 const before=await run(`(()=>{const r=document.querySelector('.developer-toggle').getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})()`);await click('Developer Tools');const after=await run(`(()=>{const r=document.querySelector('.developer-toggle').getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})()`);assert.deepEqual(after,before);await wait(`!!document.querySelector('.developer-docs-link:not([hidden])')`);assert.equal(await run(`document.querySelector('.developer-docs-link').getAttribute('href')`),'/api-docs/');
 await click('Explore tenant workspace');await wait(`!!document.querySelector('.home-developer-row .developer-docs-link:not([hidden])')`);await screenshot('developer-tools-desktop');
 await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await screenshot('developer-tools-mobile');assert.equal(await run('document.documentElement.scrollWidth<=innerWidth'),true);
 const mobileBefore=await run(`(()=>{const r=document.querySelector('.developer-toggle').getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})()`);await click('Developer Tools');const mobileAfter=await run(`(()=>{const r=document.querySelector('.developer-toggle').getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})()`);assert.deepEqual(mobileAfter,mobileBefore);assert.equal(await run(`!!document.querySelector('.developer-docs-link:not([hidden])')`),false);await run(`[...document.querySelectorAll('nav button')].find(b=>b.textContent.includes('My lease')).click()`);await wait(`!document.querySelector('[role=switch]')`);assert.deepEqual(errors,[]);console.log('PASS: developer tools toggle starts off, reveals API Docs, survives login/profile UI, hides on toggle off and has no mobile overflow/runtime errors.');
}finally{socket.close()}
