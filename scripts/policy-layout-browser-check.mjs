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
 await call('Runtime.enable');await call('Page.enable');await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});await call('Page.navigate',{url:'http://localhost:5174/'});await click('Explore customer workspace');await click('My documents');await wait(`!!document.querySelector('.policy-row')`);await run('document.fonts.ready.then(()=>true)');
 const desktop=await run(`(()=>{return [...document.querySelectorAll('.policy-row')].map(row=>{const title=row.querySelector('h3').getBoundingClientRect(),icon=row.querySelector('.document-icon').getBoundingClientRect(),buttons=[...row.querySelectorAll('.policy-reader-actions button')].map(b=>b.getBoundingClientRect());return {titleX:title.x,titleY:title.y,iconY:icon.y,buttonY:buttons[0].y,otherY:buttons[1].y,height:row.getBoundingClientRect().height}})})()`);
 for(const row of desktop){assert.ok(Math.abs(row.iconY-row.titleY)<1);assert.ok(Math.abs(row.buttonY-row.otherY)<1);assert.ok(Math.abs(row.buttonY-row.titleY)<1);assert.ok(row.height<175)}
 assert.equal(new Set(desktop.map(r=>r.titleX)).size,1);
 await run(`document.querySelector('.policy-list').scrollIntoView({block:'start'})`);await screenshot('policy-aligned-desktop');await click('Review status');await wait(`!!document.querySelector('.review-steps')`);await close();await click('Read excerpt');await wait(`!!document.querySelector('dialog blockquote')`);await close();
 for(const width of [768,390,320]){
  await call('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:width<500});await new Promise(r=>setTimeout(r,500));assert.ok(await run('document.documentElement.scrollWidth<=innerWidth'),JSON.stringify(await run('({width:innerWidth,scroll:document.documentElement.scrollWidth})')));
  assert.ok(await run(`(()=>{const row=document.querySelector('.policy-row');return Math.abs(row.querySelector('.policy-actions').getBoundingClientRect().left-row.querySelector('.policy-main').getBoundingClientRect().left)<1})()`));
  if(width===390){await run(`document.querySelector('.policy-list').scrollIntoView({block:'start'})`);await screenshot('policy-aligned-mobile')}
 }
 await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});await click('Switch demo profile');await click('Landlord');await click('Explore landlord workspace');await click('Policy library');await wait(`!!document.querySelector('.policy-version-actions')`);assert.ok(await run(`(()=>{const r=document.querySelector('.policy-row');return r.querySelectorAll('.policy-reader-actions button').length===2&&r.querySelectorAll('.policy-version-actions button').length===2})()`));await run(`document.querySelector('.policy-list').scrollIntoView({block:'start'})`);await screenshot('policy-aligned-landlord');assert.deepEqual(errors,[]);
 console.log('PASS: consistent desktop icon/title/action alignment and compact rows, mobile/tablet alignment with no overflow, working review/excerpt dialogs, and landlord version actions.');
}finally{socket.close()}
