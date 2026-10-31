import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {normalizeApiBase} from '../src/lib/apiBase.js';
import {operations,prepareRequest,executeRequest} from '../src/api-docs/client.js';
import {createHttpGateway} from '../src/services/httpGateway.js';
const spec=JSON.parse(await readFile(new URL('../../contracts/openapi.json',import.meta.url),'utf8'));
const ops=operations(spec),operation=path=>ops.find(o=>o.path===path);
const session={data:{user:null,csrfToken:null}};

test('explorer enumerates the shared spec and normalizes local/remote API bases',()=>{
 assert.equal(ops.length,11);assert.equal(normalizeApiBase(' /api/v1/ '),'/api/v1');
 assert.equal(normalizeApiBase('https://api.example.com/api/v1/'),'https://api.example.com/api/v1');
 for(const value of ['//example.com/api','javascript:alert(1)','https://user:pass@example.com/api','https://api.example.com/api?token=x','/api#fragment','/api\\evil'])assert.throws(()=>normalizeApiBase(value));
});

test('JSON requests validate before sending and cookies/CSRF/path IDs are preserved',()=>{
 const options={spec,operation:operation('/properties'),base:'https://api.example.com/api/v1/',csrfToken:'test-csrf'};
 assert.throws(()=>prepareRequest({...options,json:'invalid'}),/valid JSON/);
 assert.throws(()=>prepareRequest({...options,json:'{}'}),/Check request/);
 assert.throws(()=>prepareRequest({...options,csrfToken:'',json:'{}'}),/session/);
 const request=prepareRequest({...options,json:JSON.stringify({name:'Oak House',address:'1 Oak Street',city:'Raleigh',state:'NC',units:2})});
 assert.equal(request.url,'https://api.example.com/api/v1/properties');assert.equal(request.init.credentials,'include');assert.equal(request.init.headers['X-CSRF-Token'],'test-csrf');
 const lease=prepareRequest({spec,operation:operation('/leases/{id}'),base:'/api/v1',params:{id:'lease/foreign?x'}});
 assert.equal(lease.url,'/api/v1/leases/lease%2Fforeign%3Fx');
 assert.throws(()=>prepareRequest({spec,operation:operation('/leases/{id}'),base:'/api/v1'}),/Enter id/);
});

test('multipart requests use a real binary part, NC tag, version and browser-generated boundary',()=>{
 const request=prepareRequest({spec,operation:operation('/policies'),base:'/api/v1',csrfToken:'token',file:new File(['%PDF-test'],'rules.pdf',{type:'application/pdf'}),fields:{familyId:'family-1',expectedVersion:'2',state:'NC',effectiveFrom:'2026-11-02'}});
 assert.equal(request.init.body.get('file').name,'rules.pdf');assert.equal(request.init.body.get('expectedVersion'),'2');assert.equal(request.init.body.get('state'),'NC');assert.equal(request.init.headers['Content-Type'],undefined);
 assert.throws(()=>prepareRequest({spec,operation:operation('/policies'),base:'/api/v1',csrfToken:'token',fields:{}}),/Check request/);
});

test('response validator distinguishes success, valid errors, malformed envelopes and undocumented status',async()=>{
 const selected=operation('/auth/session'),request=prepareRequest({spec,operation:selected,base:'/api/v1'});
 const run=(status,body)=>executeRequest({spec,operation:selected,request,fetcher:async()=>new Response(body,{status,headers:{'Content-Type':'application/json'}})});
 const success=await run(200,JSON.stringify(session));assert.equal(success.validation.valid,true);assert.equal(success.ok,true);
 const error=await run(401,JSON.stringify({error:{code:'UNAUTHENTICATED',message:'Sign in.',requestId:'test',fields:{}}}));assert.equal(error.validation.valid,true);assert.equal(error.ok,false);
 assert.equal((await run(200,JSON.stringify({user:null}))).validation.valid,false);
 assert.equal((await run(200,'<html>Wrong route</html>')).validation.valid,false);
 assert.equal((await run(201,JSON.stringify(session))).validation.valid,false);
 const wrongType=await executeRequest({spec,operation:selected,request,fetcher:async()=>new Response(JSON.stringify(session),{headers:{'Content-Type':'text/plain'}})});assert.equal(wrongType.validation.valid,false);
});

test('network and canceled requests explain connection failure',async()=>{
 const selected=operation('/auth/session'),request=prepareRequest({spec,operation:selected,base:'/api/v1'});
 await assert.rejects(executeRequest({spec,operation:selected,request,fetcher:async()=>{throw Error('network')}}),/CORS/);
 const controller=new AbortController();controller.abort();
 await assert.rejects(executeRequest({spec,operation:selected,request,signal:controller.signal,fetcher:async()=>{throw Error('abort')}}),/canceled/);
});

test('application adapter connects to a separately hosted API with normalized paths',async()=>{
 let call;const gateway=createHttpGateway({base:'https://api.example.com/api/v1/',fetcher:async(url,init)=>{call={url,init};return {ok:true,json:async()=>session}}});
 await gateway.getSession();assert.equal(call.url,'https://api.example.com/api/v1/auth/session');assert.equal(call.init.credentials,'include');
});
