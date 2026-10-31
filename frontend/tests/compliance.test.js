import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {answerReviewMatches,officialSources} from '../src/lib/compliance.js';
import {createHttpGateway} from '../src/services/httpGateway.js';
const now=Date.parse('2026-10-31T12:00:00Z');
const request={asOf:'2026-10-31',scope:{type:'lease',id:'lease-1'}};
const answer='Reviewed answer';
const valid=()=>({answer,status:'supported',compliance:{status:'passed',state:'NC',asOf:request.asOf,kind:'answer',scopeKey:'lease:lease-1',checkedAt:'2026-10-31T11:00:00Z',expiresAt:'2026-11-01T11:00:00Z',lawRevision:'a'.repeat(64),contentHash:createHash('sha256').update(answer).digest('hex'),citations:[{url:officialSources[0].url,section:'42-42'}]}});
test('answer review binds final text, state, date, scope and current official sources',async()=>{
 assert.equal(await answerReviewMatches(valid(),request,{now}),true);
 for(const patch of [{state:'TX'},{asOf:'2026-10-30'},{scopeKey:'lease:lease-2'},{kind:'policy'},{expiresAt:'2026-10-31T12:00:00Z'},{checkedAt:'2026-11-01T12:00:00Z'},{contentHash:'b'.repeat(64)},{lawRevision:''},{citations:[{url:'https://example.com',section:'42'}]},{findings:[{message:'Conflict'}]}]){
  const item=valid();Object.assign(item.compliance,patch);assert.equal(await answerReviewMatches(item,request,{now}),false,JSON.stringify(patch));
 }
 const changed=valid();changed.answer='Unreviewed replacement';assert.equal(await answerReviewMatches(changed,request,{now}),false);
});
test('stale passed verdict is withheld by HTTP adapter',async()=>{
 const item=valid();item.compliance.expiresAt='2000-01-01T00:00:00Z';
 const g=createHttpGateway({fetcher:async()=>({ok:true,json:async()=>({data:item})})});
 const response=await g.ask(request);assert.equal(response.status,'needs_clarification');assert.equal(response.compliance.status,'unavailable');assert.deepEqual(response.citations,[]);
});
