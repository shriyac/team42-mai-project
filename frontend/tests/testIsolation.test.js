import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {existsSync} from 'node:fs';
import {testEnvironment,allowedSource,testPassword} from '../../scripts/run-isolated-tests.mjs';

test('credential allowlist prevents sentinel secrets from appearing in child failure output',()=>{
 const marker='FICTIONAL-LEAK-SENTINEL-NOT-A-CREDENTIAL';
 const parent={PATH:process.env.PATH,
  LAGA_BOOTSTRAP_PASSWORD:marker,PINECONE_API_KEY:marker,NEBIUS_API_KEY:marker,
  FIREWORKS_API_KEY:marker,OPENAI_API_KEY:marker,ANTHROPIC_API_KEY:marker,
  SESSION_SECRET:marker,UNRECOGNIZED_FUTURE_CREDENTIAL:marker};
 const env=testEnvironment(parent,'/tmp/fictional-home','/tmp/fictional-source');
 assert.ok(!Object.values(env).includes(marker),'Inherited secret entered the child environment');
 assert.equal(env.LAGA_BOOTSTRAP_PASSWORD,testPassword);
 // Deliberately force both Python and Node failures, never using real values.
 for(const [command,args] of [
  [process.execPath,['--input-type=module','-e',"import assert from 'node:assert/strict'; assert.equal(process.env.OPENAI_API_KEY,'deliberate-fictional-failure')"]],
  ['python',['-c',"import os; assert os.getenv('PINECONE_API_KEY') == 'deliberate-fictional-failure'"]],
 ]){
  const result=spawnSync(command,args,{env,encoding:'utf8'});
  assert.ok(result.status!==0,'Deliberate failure did not occur');
  assert.ok(!(result.stdout+result.stderr).includes(marker),'Failure diagnostics leaked a sentinel');
 }
});

test('test snapshot excludes private runtime files and dotenv input',()=>{
 for(const file of ['.env','.env.local','frontend/.env','data/backend.sqlite3',
  'data/demo-phase7d/backend-bootstrap-login.json','artifacts/lease_rag_local/active.json',
  'rag_bindings.json','documents.json','.streamlit/secrets.toml','credentials.pem']){
  assert.equal(allowedSource(file),false,file);
 }
 assert.equal(allowedSource('src/laga/api.py'),true);
 assert.equal(allowedSource('.env.example'),true);
 assert.equal(process.env.LAGA_TEST_ISOLATED,'1','Use the isolated test runner');
 assert.equal(existsSync(new URL('../../data/demo-phase7d/backend-bootstrap-login.json',import.meta.url)),false);
 assert.equal(existsSync(new URL('../../.env',import.meta.url)),false);
});
