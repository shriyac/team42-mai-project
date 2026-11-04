import test from 'node:test';
import assert from 'node:assert/strict';
import {stateVerificationEnabled} from '../src/lib/features.js';
import {createMockGateway} from '../src/services/mockGateway.js';
import {createHttpGateway} from '../src/services/httpGateway.js';
import {resolvePolicies} from '../src/lib/policies.js';
import {policies,AS_OF} from '../src/data/fixtures.js';

test('state verification defaults off and can be enabled for either workspace role',async()=>{
 assert.equal(stateVerificationEnabled,false);
 for(const role of ['landlord','tenant'])for(const enabled of [undefined,true]){
  const gateway=createMockGateway({delay:0,...(enabled===undefined?{}:{stateVerification:enabled})});
  await gateway.login({role,tenantId:'tenant-1'});
  const answer=await gateway.ask({question:'When does my lease end?',scope:{type:'lease',id:'lease-1'},asOf:AS_OF});
  assert.equal(answer.status,enabled?'needs_clarification':'supported');
  assert.equal(answer.citations.length>0,!enabled);
 }
});
test('HTTP review gating is optional but never overrides a backend refusal',async()=>{
 const request={question:'notice',scope:{type:'lease',id:'lease-1'},asOf:AS_OF};
 for(const enabled of [false,true]){
  const item={status:'supported',answer:'Document excerpt',citations:[]};
  const gateway=createHttpGateway({stateVerification:enabled,fetcher:async()=>({ok:true,json:async()=>({data:item})})});
  assert.equal((await gateway.ask(request)).status,enabled?'needs_clarification':'supported');
 }
 const refused={status:'needs_clarification',answer:'Backend review pending',citations:[]};
 const gateway=createHttpGateway({fetcher:async()=>({ok:true,json:async()=>({data:refused})})});
 assert.deepEqual(await gateway.ask(request),refused);
});
test('disabled review still requires ready processing, matching state and current effective dates',()=>{
 const policy=policies.find(p=>p.status==='ready'&&p.effectiveFrom<=AS_OF&&(!p.effectiveTo||p.effectiveTo>AS_OF));
 assert.ok(policy);
 const options={asOf:AS_OF,propertyId:policy.propertyId,state:'NC'};
 assert.equal(resolvePolicies([policy],options).eligible.length,1);
 assert.equal(resolvePolicies([policy],{...options,stateVerification:true}).eligible.length,0);
 for(const changed of [{status:'awaiting_backend'},{state:'TX'},{effectiveFrom:'2099-01-01'},{effectiveTo:AS_OF}])assert.equal(resolvePolicies([{...policy,...changed}],options).eligible.length,0);
});
