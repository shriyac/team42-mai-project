import test from 'node:test';
import assert from 'node:assert/strict';
import {askWithTiming,formatResponseTime} from '../src/lib/responseTiming.js';

test('response timing spans asynchronous gateway work and preserves answer data',async()=>{
 let clock=100,finish;
 const input={question:'Rent?',scope:{type:'lease',id:'lease-1'}};
 const answer={id:'answer-1',answer:'Source-backed answer',citations:[{id:'source-1'}],responseTimeMs:999999};
 const gateway={ask:async request=>{assert.equal(request,input);await new Promise(resolve=>finish=resolve);return answer}};
 const pending=askWithTiming(gateway,input,{now:()=>clock});
 clock=2345;finish();
 const measured=await pending;
 assert.deepEqual(measured,{...answer,responseTimeMs:2245});
 assert.equal(answer.responseTimeMs,999999);
 assert.equal(formatResponseTime(measured.responseTimeMs),'Responded in 2.25s');
});
test('response timing supports immediate and long answers and hides missing timing',()=>{
 assert.equal(formatResponseTime(0),'Responded in 0.00s');
 assert.equal(formatResponseTime(125),'Responded in 0.13s');
 assert.equal(formatResponseTime(125000),'Responded in 125.00s');
 for(const value of [undefined,null,NaN,Infinity,-1])assert.equal(formatResponseTime(value),null);
});
test('failed requests propagate the original error without fabricating an agent response',async()=>{
 const failure=new Error('Backend unavailable');
 await assert.rejects(askWithTiming({ask:async()=>{throw failure}},{},{now:()=>100}),error=>error===failure);
});

test('timing includes submission work before the gateway call',async()=>{
 const answer=await askWithTiming({ask:async()=>({answer:'Done'})},{},{startedAt:100,now:()=>650});
 assert.equal(answer.responseTimeMs,550);
});
