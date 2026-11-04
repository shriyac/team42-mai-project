import Ajv from 'ajv/dist/2020.js';
import {normalizeApiBase} from '../lib/apiBase.js';

export function operations(spec){return Object.entries(spec.paths).flatMap(([path,item])=>Object.entries(item).filter(([method])=>['get','post','put','patch','delete'].includes(method)).map(([method,operation])=>({path,method,...operation})))}
export function dereference(spec,schema){return schema?.$ref?schema.$ref.slice(2).split('/').reduce((node,key)=>node[key],spec):schema}
export function createValidator(spec){
 const ajv=new Ajv({strict:false,allErrors:true,validateFormats:false});
 const cache=new Map();
 return (schema,value)=>{
  if(!schema)return {valid:false,errors:['No schema is defined for this response.']};
  let validate=cache.get(schema);if(!validate){validate=ajv.compile({...schema,components:spec.components});cache.set(schema,validate)}
  const valid=validate(value);return {valid,errors:valid?[]:validate.errors.map(e=>`${e.instancePath||'/'} ${e.message}`)};
 };
}
export function prepareRequest({spec,operation,base,params={},json='',fields={},file=null,csrfToken=''}){
 let path=operation.path;
 for(const parameter of operation.parameters||[]){
  if(parameter.in==='path'){if(!params[parameter.name]?.trim())throw new Error(`Enter ${parameter.name}.`);path=path.replace('{'+parameter.name+'}',encodeURIComponent(params[parameter.name].trim()))}
  if(parameter.in==='header'&&parameter.name==='X-CSRF-Token'&&parameter.required&&!csrfToken.trim())throw new Error('Get a session or sign in first, or enter the CSRF token supplied by your backend.');
 }
 const headers={Accept:'application/json'};if(operation.method!=='get'&&csrfToken)headers['X-CSRF-Token']=csrfToken;
 const content=operation.requestBody?.content;let body,value,schema;
 if(content?.['application/json']){
  try{value=JSON.parse(json)}catch{throw new Error('Request body must be valid JSON.')}
  schema=content['application/json'].schema;headers['Content-Type']='application/json';body=JSON.stringify(value);
 }else if(content?.['multipart/form-data']){
  schema=content['multipart/form-data'].schema;const resolved=dereference(spec,schema);value={};body=new FormData();
  for(const [key,definition] of Object.entries(resolved.properties)){
   if(definition.format==='binary'){if(file){if(!file.size||file.size>10*1024*1024||!file.name.toLowerCase().endsWith('.pdf'))throw new Error('Choose a nonempty PDF up to 10 MB.');body.append(key,file);value[key]=file.name}}
   else if(fields[key]!==undefined&&fields[key]!==''){value[key]=definition.type==='integer'?Number(fields[key]):fields[key];body.append(key,String(value[key]))}
  }
 }
 if(schema){const result=createValidator(spec)(schema,value);if(!result.valid)throw new Error('Check request: '+result.errors.join('; '))}
 return {url:normalizeApiBase(base)+path,init:{method:operation.method.toUpperCase(),credentials:'include',headers,...(body?{body}:{})}};
}
export async function executeRequest({spec,operation,request,fetcher=fetch,signal}){
 const start=performance.now();let response;
 try{response=await fetcher(request.url,{...request.init,signal,redirect:'error'})}catch(error){if(signal?.aborted)throw new Error('Request canceled or timed out.');throw new Error('Cannot reach this API. Check its URL, TLS certificate, server availability and credentialed CORS settings. The browser console may provide details.')}
 let raw;try{raw=await response.text()}catch{throw new Error(signal?.aborted?'Request canceled or timed out.':'The connection closed before the response could be read.')}
 let data;try{data=JSON.parse(raw)}catch{}
 const schema=operation.responses[String(response.status)]?.content?.['application/json']?.schema;
 const isJson=response.headers.get('content-type')?.split(';')[0].trim().toLowerCase()==='application/json';
 const validation=!isJson||data===undefined?{valid:false,errors:['Expected an application/json response envelope.']}:createValidator(spec)(schema,data);
 return {status:response.status,ok:response.ok,duration:Math.round(performance.now()-start),data,raw,validation,url:request.url,headers:Object.fromEntries(response.headers.entries())};
}
