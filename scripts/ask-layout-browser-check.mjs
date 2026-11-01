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
 await call('Runtime.enable');await call('Page.enable');await call('Page.navigate',{url:'http://localhost:5174/'});await click('Explore tenant workspace');await click('Ask Laga');await wait(`!!document.querySelector('.question-composer')`);await run('document.fonts.ready.then(()=>true)');
 for(const [width,height]of [[1440,900],[1280,720],[1024,768],[390,844],[390,640]]){
  await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});await run('window.scrollTo(0,0)');await new Promise(r=>setTimeout(r,200));
  const layout=await run(`(()=>{const c=document.querySelector('.question-composer').getBoundingClientRect();return {top:c.top,bottom:c.bottom,height:innerHeight,overflow:document.documentElement.scrollWidth>innerWidth}})()`);
  assert.equal(layout.overflow,false);assert.ok(layout.bottom<=height+1,JSON.stringify({width,height,...layout}));assert.ok(layout.top>=0);if(width>=901)assert.ok(await run('document.documentElement.scrollHeight<=innerHeight+1'),'Desktop Ask page must fit the viewport');if(width===1440||height===640)await screenshot('ask-compact-'+width+'x'+height);
 }
 await call('Emulation.setDeviceMetricsOverride',{width:1280,height:720,deviceScaleFactor:1,mobile:false});
 await click('Can I bring a pet?');await wait(`!!document.querySelector('.chat-answer')`);
 for(let i=0;i<5;i++){await run(`(()=>{const input=document.querySelector('#question');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(input,'What is the deposit policy?');input.dispatchEvent(new Event('input',{bubbles:true}))})()`);await run(`document.querySelector('.question-composer').requestSubmit()`);await wait(`!document.querySelector('.send-button').disabled||!document.querySelector('.thinking')`);await new Promise(r=>setTimeout(r,300))}
 assert.ok(await run(`document.querySelector('.chat-messages').scrollHeight>document.querySelector('.chat-messages').clientHeight`));
 assert.ok(await run(`document.querySelector('.question-composer').getBoundingClientRect().bottom<=innerHeight`));await screenshot('ask-compact-conversation');await click('Switch demo profile');await click('Landlord');await click('Explore landlord workspace');await click('Ask Laga');for(const [width,height]of [[1280,720],[390,640]]){await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});await run('window.scrollTo(0,0)');await new Promise(r=>setTimeout(r,200));assert.ok(await run('document.querySelector(".question-composer").getBoundingClientRect().bottom<=innerHeight'),'Landlord composer must fit');}assert.deepEqual(errors,[]);
 console.log('PASS: composer visible without page scrolling at five desktop/mobile sizes; long conversations scroll internally; no horizontal overflow or runtime errors.');
}finally{socket.close()}
