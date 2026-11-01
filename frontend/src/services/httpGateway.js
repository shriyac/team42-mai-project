import {stateVerificationEnabled} from '../lib/features.js';
import {normalizeApiBase} from '../lib/apiBase.js';
import {answerReviewMatches} from '../lib/compliance.js';
import {ApiError} from './errors.js';
export function createHttpGateway({base='/api/v1',fetcher=fetch,stateVerification=stateVerificationEnabled}={}){
 base=normalizeApiBase(base);
 let csrfToken=null;
 async function request(path,{method='GET',body}={}){
  const form=typeof FormData!=='undefined'&&body instanceof FormData;
  let response;try{response=await fetcher(base+path,{method,credentials:'include',headers:{Accept:'application/json',...(body&&!form?{'Content-Type':'application/json'}:{}),...(method!=='GET'&&csrfToken?{'X-CSRF-Token':csrfToken}:{})},...(body?{body:form?body:JSON.stringify(body)}:{})})}catch{throw new ApiError('We could not reach Laga. Check your connection and try again.',{code:'NETWORK_ERROR'})}
  let result;try{result=await response.json()}catch{throw new ApiError('The service returned an unreadable response. Please try again.',{code:'INVALID_RESPONSE'})}
  if(!response.ok){if(response.status===401&&typeof window!=='undefined')window.dispatchEvent(new Event('laga:session-expired'));throw new ApiError(result.error?.message||'Something went wrong. Please try again.',{code:result.error?.code,requestId:result.error?.requestId,fields:result.error?.fields})}
  if(result.data===undefined)throw new ApiError('The response did not match the Laga interface contract.',{code:'INVALID_RESPONSE'});
  return result.data;
 }
 return {mode:'api',listDemoUsers:async()=>({tenants:[],landlord:null}),
 async login({email,password}){const session=await request('/auth/login',{method:'POST',body:{email,password}});csrfToken=session.csrfToken;return session},
 async getSession(){const session=await request('/auth/session');csrfToken=session.csrfToken;return session},
 async logout(){await request('/auth/logout',{method:'POST',body:{}});csrfToken=null},
 createProperty:body=>request('/properties',{method:'POST',body}),
 getWorkspace:()=>request('/workspace'),getLease:id=>request('/leases/'+encodeURIComponent(id)),
 ask:async body=>{const result=await request('/assistant/messages',{method:'POST',body});if(stateVerification&&result.status==='supported'&&!(await answerReviewMatches(result,body)))return {...result,status:'needs_clarification',answer:'State-law validation is unavailable. Please request a review before relying on lease or policy guidance.',citations:[],calculations:[],compliance:{status:'unavailable',state:'NC'},activity:[{label:'State-law review could not be verified for this answer',status:'attention'}]};return result},
 createRequest:body=>request('/requests',{method:'POST',body}),
 replyRequest:(id,body)=>request('/requests/'+encodeURIComponent(id)+'/reply',{method:'POST',body}),
 uploadPolicy:({file,category,propertyId,familyId,title,effectiveFrom,expectedVersion,state})=>{const body=new FormData();body.append('file',file);if(state)body.append('state',state);if(category)body.append('category',category);if(propertyId)body.append('propertyId',propertyId);if(familyId)body.append('familyId',familyId);if(title)body.append('title',title);body.append('effectiveFrom',effectiveFrom);if(expectedVersion!==undefined)body.append('expectedVersion',String(expectedVersion));return request('/policies',{method:'POST',body})},
 deletePolicy:id=>request('/policies/'+encodeURIComponent(id),{method:'DELETE'})
 };
}
