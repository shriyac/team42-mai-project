import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base=process.env.LAGA_LOGIN_TEST_URL||'http://localhost:5185/';
const targets=await(await fetch(`http://127.0.0.1:${process.env.LAGA_BROWSER_PORT||9224}/json`)).json();
const target=targets.find(t=>t.type==='page'&&!t.url.startsWith('edge:'));
assert.ok(target,'Open the app in a browser with remote debugging on port 9224.');
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}));
let id=0;const pending=new Map(),errors=[];let loginRequests=0;
socket.addEventListener('message',event=>{const m=JSON.parse(event.data);if(m.id){const job=pending.get(m.id);pending.delete(m.id);if(!job)return;m.error?job.reject(m.error):job.resolve(m.result)}if(m.method==='Network.requestWillBeSent'&&m.params.request.url.endsWith('/auth/login'))loginRequests++;if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails)});
const call=(method,params={})=>new Promise((resolve,reject)=>{const next=++id;const timer=setTimeout(()=>{pending.delete(next);reject(new Error('Browser command timed out: '+method))},15000);pending.set(next,{resolve:value=>{clearTimeout(timer);resolve(value)},reject:error=>{clearTimeout(timer);reject(error)}});socket.send(JSON.stringify({id:next,method,params}))});
const run=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value};
const wait=async expression=>{const end=Date.now()+7000;while(Date.now()<end){if(await run(expression))return;await new Promise(r=>setTimeout(r,100))}throw Error('Timed out: '+expression)};
const click=async text=>{await wait(`[...document.querySelectorAll('button')].some(b=>!b.disabled&&b.textContent.trim().startsWith(${JSON.stringify(text)}))`);await run(`(()=>{const button=[...document.querySelectorAll('button')].find(b=>b.textContent.trim().startsWith(${JSON.stringify(text)}));button.focus();button.click()})()`)};

const round=Number(process.env.LAGA_LOGIN_TEST_ROUND||1);
const credentials=JSON.parse(await fs.readFile(process.env.LAGA_LOGIN_TEST_CREDENTIALS||new URL('../data/backend-bootstrap-login.json',import.meta.url),'utf8'));
const fill=async(name,value)=>run(`(()=>{const el=document.querySelector('[name="${name}"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('input',{bubbles:true}))})()`);
const reset=async()=>{await run(`(async()=>{const s=await(await fetch('/api/v1/auth/session')).json();if(s.data.user)await fetch('/api/v1/auth/logout',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':s.data.csrfToken},body:'{}'})})()`);await call('Page.navigate',{url:base});await wait(`document.querySelectorAll('.login-option').length===2`)};
try{
 await call('Runtime.enable');await call('Page.enable');await call('Network.enable');await call('Page.navigate',{url:base});await wait(`!!document.querySelector('.login-page')||!!document.querySelector('nav')`);await reset();
 assert.equal(await run(`document.querySelectorAll('.login-card input,.login-card select,.profile-static').length`),0);
 for(const role of ['tenant','landlord']){
  await click(role==='tenant'?'Tenant login':'Landlord login');
  await wait(`!!document.querySelector('[name=email]')`);
  assert.equal(await run(`document.querySelector('[name=email]').value+document.querySelector('[name=password]').value`),'');
  await fill('email','unused@example.test');await fill('password','temporary');
  await click('Back to login options');await click(role==='tenant'?'Tenant login':'Landlord login');
  assert.equal(await run(`document.querySelector('[name=email]').value+document.querySelector('[name=password]').value`),'');
  const account=credentials.accounts.find(a=>a.role===role);assert.ok(account);
  await fill('email',account.email);await fill('password','incorrect-password');await click('Sign in');
  await wait(`!!document.querySelector('[role=alert]')`);
  assert.equal(await run(`document.querySelector('[name=password]').type`),'password');
  await fill('password',credentials.password);await click('Sign in');
  await wait(`!document.querySelector('.login-page')`);
  assert.equal(await run(`fetch('/api/v1/auth/session').then(r=>r.json()).then(s=>s.data.user.role)`),role);
  await reset();
 }

 if(round===2){
  await click('Tenant login');
  for(const [email,password] of [['',''],['not-an-email','x'],['maya@example.test','']]){
   await fill('email',email);await fill('password',password);assert.equal(await run(`document.querySelector('form').checkValidity()`),false);
  }
  await fill('email','unknown@example.test');await fill('password',credentials.password);await click('Sign in');await wait(`!!document.querySelector('[role=alert]')`);
  assert.equal(await run(`fetch('/api/v1/auth/session').then(r=>r.json()).then(s=>s.data.user)`),null);
  await call('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  await click('Sign in');await wait(`document.querySelector('[role=alert]')?.textContent.includes('could not reach')`);
  assert.equal(await run(`document.querySelector('[type=submit]').disabled`),false);
  await call('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});await reset();
 }
 if(round===3){
  // Select landlord UI with tenant credentials: permissions must remain tenant-owned.
  await click('Landlord login');const account=credentials.accounts.find(a=>a.role==='tenant');
  await fill('email',account.email.toUpperCase());await fill('password',credentials.password);
  loginRequests=0;
  await run(`(()=>{const f=document.querySelector('form');f.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));f.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))})()`);
  assert.equal(await run(`document.querySelector('[name=email]').disabled&&document.querySelector('.login-back').disabled`),true);
  await wait(`!document.querySelector('.login-page')`);assert.equal(loginRequests,1);
  assert.equal(await run(`fetch('/api/v1/auth/session').then(r=>r.json()).then(s=>s.data.user.role)`),'tenant');
  await call('Page.reload');await wait(`!!document.querySelector('nav')`);
  assert.equal(await run(`fetch('/api/v1/auth/session').then(r=>r.json()).then(s=>s.data.user.email)`),account.email);await reset();
  assert.equal(await run(`fetch('/api/v1/workspace').then(r=>r.status)`),401);
 }
 await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
 assert.equal(await run('document.documentElement.scrollWidth<=innerWidth'),true);await click('Tenant login');
 assert.equal(await run('document.documentElement.scrollWidth<=innerWidth'),true);
 assert.deepEqual(errors,[]);
 console.log(`PASS round ${round}: role choices, blank/reset forms, invalid-password recovery, tenant/landlord sign-in, mobile layout; ${round===1?'happy path and credential recovery':round===2?'required fields, malformed email, unknown account, network failure recovery':'duplicate submission, uppercase email, role boundary, reload persistence, logout protection'}.`);
}finally{await call('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});await call('Emulation.clearDeviceMetricsOverride');socket.close()}
