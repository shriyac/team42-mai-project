import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import Ajv from 'ajv/dist/2020.js';
import {createHash} from 'node:crypto';

const read=path=>readFile(new URL(path,import.meta.url),'utf8').then(JSON.parse);
test('backend handoff request examples and reviewed response match the OpenAPI schemas',async()=>{
 const spec=await read('../../contracts/openapi.json'),examples=await read('../../contracts/integration-examples.json');
 const ajv=new Ajv({strict:false,validateFormats:false});ajv.addSchema({$id:'handoff',components:spec.components});
 const check=(name,value)=>{const validate=ajv.compile({$ref:'handoff#/components/schemas/'+name});assert.ok(validate(value),name+': '+JSON.stringify(validate.errors))};
 for(const [key,name] of Object.entries({login:'LoginInput',propertyRegistration:'PropertyRegistration',ask:'AskInput',newPolicyMultipart:'PolicyUpload',newVersionMultipart:'PolicyUpload',clarificationRequest:'RequestInput',landlordReply:'ReplyInput'}))check(name,examples[key]);
 check('Answer',examples.illustrativePassedAnswer.data);
 assert.equal(examples.illustrativePassedAnswer.data.compliance.contentHash,createHash('sha256').update(examples.illustrativePassedAnswer.data.answer).digest('hex'));
 const validate=ajv.compile({$ref:'handoff#/components/schemas/Compliance'});
 assert.equal(validate({status:'passed'}),false,'A bare passed flag must not satisfy the contract.');
 const operation=spec.paths['/properties'].post;
 assert.deepEqual(operation.security,spec.paths['/policies'].post.security);
 assert.ok(operation.parameters.some(p=>p.name==='X-CSRF-Token'&&p.required));
 for(const code of ['401','403','409','422','503'])assert.ok(operation.responses[code]);
});

test('PDF guide examples and recorded contract snapshot match the current specification',async()=>{
 const spec=await read('../../contracts/openapi.json');
 const examples=await read('../../docs/integration-guide-examples.json');
 const manifest=await read('../../docs/integration-guide-manifest.json');
 const ajv=new Ajv({strict:false,validateFormats:false});ajv.addSchema({$id:'pdf-guide',components:spec.components});
 for(const [name,{schema,value}] of Object.entries(examples)){
  const validate=ajv.compile({$ref:'pdf-guide#/components/schemas/'+schema});
  assert.ok(validate(value),name+': '+JSON.stringify(validate.errors));
 }
 const bytes=await readFile(new URL('../../contracts/openapi.json',import.meta.url));
 // Git imports may normalize Windows line endings without changing the contract.
 const specText=bytes.toString('utf8');
 const hashes=[specText.replace(/\r\n/g,'\n'),specText.replace(/\r?\n/g,'\r\n')]
  .map(text=>createHash('sha256').update(text).digest('hex'));
 assert.ok(hashes.includes(manifest.specSha256),'Recorded contract checksum must match LF or CRLF source');
 assert.equal(manifest.endpointCount,Object.values(spec.paths).reduce((count,item)=>count+Object.keys(item).length,0));
 assert.equal(manifest.modelCount,Object.keys(spec.components.schemas).length);
});
