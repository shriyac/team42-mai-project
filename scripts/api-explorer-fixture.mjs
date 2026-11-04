// Test-only backend for browser QA. Never import this into the application.
import http from 'node:http';
import {readFile} from 'node:fs/promises';
const fixtures=JSON.parse(await readFile(new URL('../contracts/examples.json',import.meta.url),'utf8'));
const session={...fixtures.session.data,csrfToken:'fixture-csrf'};
const error=(message)=>({error:{code:'VALIDATION_ERROR',message,requestId:'fixture-request',fields:{}}});
const server=http.createServer(async(req,res)=>{
 const origin=req.headers.origin;
 if(origin==='http://localhost:5174')res.setHeader('Access-Control-Allow-Origin',origin);
 res.setHeader('Access-Control-Allow-Credentials','true');res.setHeader('Vary','Origin');
 res.setHeader('Access-Control-Allow-Headers','Content-Type, X-CSRF-Token');res.setHeader('Access-Control-Allow-Methods','GET, POST, DELETE, OPTIONS');
 if(req.method==='OPTIONS'){res.writeHead(204);return res.end()}
 res.setHeader('Content-Type','application/json');
 const send=(code,body)=>{res.writeHead(code);res.end(JSON.stringify(body))};
 let raw='';for await(const chunk of req){raw+=chunk;if(raw.length>1024*1024)return send(413,error('Fixture limit.'))}
 const signedIn=req.headers.cookie?.includes('laga_session=explorer-fixture');
 if(req.url==='/api/v1/auth/session')return send(200,{data:signedIn?session:{user:null,csrfToken:null}});
 if(req.url==='/api/v1/auth/login'){
  let body;try{body=JSON.parse(raw)}catch{return send(400,error('Invalid JSON.'))}
  if(body.email!=='alex@alderliving.example'||body.password!=='fixture-password')return send(401,error('Invalid test credentials.'));
  res.setHeader('Set-Cookie','laga_session=explorer-fixture; HttpOnly; SameSite=Lax; Path=/');return send(200,{data:session});
 }
 if(!signedIn)return send(401,error('Sign in.'));
 if(req.method!=='GET'&&req.headers['x-csrf-token']!=='fixture-csrf')return send(403,error('CSRF token required.'));
 if(req.url==='/api/v1/auth/logout'){res.setHeader('Set-Cookie','laga_session=; Max-Age=0; HttpOnly; Path=/');return send(200,{data:{signedOut:true}})}
 if(req.url==='/api/v1/workspace')return send(200,fixtures.workspace);
 if(req.url==='/api/v1/properties'){
  const input=JSON.parse(raw);return send(200,{data:{id:'fixture-property',...input,style:'willow',amenities:[]}});
 }
 if(req.url==='/api/v1/policies'){
  if(!req.headers['content-type']?.includes('multipart/form-data; boundary=')||!raw.includes('%PDF-')||!raw.includes('name="state"\r\n\r\nNC'))return send(422,error('Expected binary PDF and NC multipart tag.'));
  return send(200,{data:{...fixtures.workspace.data.policies[0],id:'fixture-policy',status:'uploaded',compliance:{status:'pending',state:'NC'}}});
 }
 if(req.url==='/api/v1/leases/bad-json'){res.setHeader('Content-Type','text/html');res.writeHead(200);return res.end('<html>Not JSON</html>')}
 if(req.url==='/api/v1/leases/lease-1')return send(200,fixtures.leaseDetail);
 return send(404,error('Not implemented by the test fixture.'));
});
server.listen(8002,'127.0.0.1',()=>console.log('Test-only explorer fixture: http://localhost:8002/api/v1'));
