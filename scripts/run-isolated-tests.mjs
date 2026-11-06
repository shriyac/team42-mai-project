// Trusted launcher: never forward the workspace environment or runtime files.
import {spawnSync} from 'node:child_process';
import {mkdtempSync,mkdirSync,copyFileSync,cpSync,symlinkSync,rmSync,existsSync,readdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=fileURLToPath(new URL('../',import.meta.url));
export const testPassword='fictional-isolated-test-password-00000001';
export function testEnvironment(parent,home,source){
 const env={};
 // Deliberately allowlist, rather than attempting to enumerate every secret.
 for(const key of ['PATH','SystemRoot','WINDIR','LD_LIBRARY_PATH','SSL_CERT_FILE','NIX_SSL_CERT_FILE']){
  if(parent[key])env[key]=parent[key];
 }
 return {...env,HOME:home,XDG_CONFIG_HOME:path.join(home,'config'),XDG_CACHE_HOME:path.join(home,'cache'),
  LANG:'C.UTF-8',TZ:'UTC',LAGA_TEST_ISOLATED:'1',PYTEST_DISABLE_PLUGIN_AUTOLOAD:'1',
  PYTHON_DOTENV_DISABLED:'1',LAGA_BOOTSTRAP_PASSWORD:testPassword,
  VITE_LAGA_MODE:'api',VITE_LAGA_API_BASE:'/api/v1',
  LAGA_DATABASE:path.join(home,'test-only.sqlite3'),
  PYTHONPATH:[path.join(source,'src'),source,
   ...(existsSync(path.join(root,'.pythonlibs/lib'))?readdirSync(path.join(root,'.pythonlibs/lib')):[]).filter(name=>/^python\d/.test(name))
    .map(name=>path.join(root,'.pythonlibs/lib',name,'site-packages'))].join(path.delimiter)};
}
export function allowedSource(file){
 if(file.split('/').some(part=>['node_modules','.git','.agents','.local','.streamlit','attached_assets','uploads','artifacts','dist','.venv','.pythonlibs'].includes(part)))return false;
 if(file.startsWith('data/'))return ['data/Free-North-Carolina-Standard-Lease-Agreement-Template.pdf','data/NC_general_statutes_Chapter_42.pdf'].includes(file);
 return !file.split('/').some(part=>/^\.env(?:\.|$)/.test(part)&&part!=='.env.example'
  || /(?:bootstrap-login|rag_bindings).*\.json$/.test(part)
  || part==='documents.json'||/\.(?:sqlite.*|db|pem|key|p12|pfx)$/.test(part));
}
export function runIsolated(mode='all',parent=process.env){
 if(!['all','verify','python','frontend','security','build','rag-config','evals'].includes(mode))throw Error('Unknown isolated test mode');
 const temp=mkdtempSync(path.join(tmpdir(),'laga-isolated-'));
 try{
  const source=path.join(temp,'source'),home=path.join(temp,'home');
  mkdirSync(source);mkdirSync(home,{mode:0o700});
  const env=testEnvironment(parent,home,source);
  const listing=spawnSync('git',['ls-files','--cached','--others','--exclude-standard','-z'],{cwd:root,env,encoding:'utf8'});
  if(listing.status!==0)throw Error('Cannot enumerate test sources');
  for(const file of new Set(listing.stdout.split('\0').filter(Boolean).filter(allowedSource))){
   const destination=path.join(source,file);mkdirSync(path.dirname(destination),{recursive:true});
   copyFileSync(path.join(root,file),destination);
  }
  symlinkSync(path.join(root,'node_modules'),path.join(source,'node_modules'),'dir');
  const run=(command,args)=>{
   const result=spawnSync(command,args,{cwd:source,env,stdio:'inherit'});
   if(result.error)throw Error('Isolated command could not start');
   return result.status??1;
  };
  if(mode==='verify')return run(process.execPath,['--test','frontend/tests/testIsolation.test.js']);
  if(mode==='security')return run(process.execPath,['--test','frontend/tests/previewSecurity.test.js','frontend/tests/testIsolation.test.js']);
  const python=existsSync(path.join(root,'.pythonlibs/bin/python'))?path.join(root,'.pythonlibs/bin/python'):'python';
  if(mode==='evals'){
   const status=run(python,['-m','evaluation.run_evals','--mode','mock']);
   if(status)return status;
   // Only the public synthetic evaluation report/results leave this isolated copy.
   for(const name of ['results.json','report.md']){
    copyFileSync(path.join(source,'evaluation',name),path.join(root,'evaluation',name));
   }
   return 0;
  }
  if(mode==='rag-config')return run(python,['-m','pytest','-q','--tb=short',
   'tests/test_rag_target_configuration.py','tests/test_production_rag.py','tests/test_synthetic_demo.py']);
  // Launcher tests require the real frontend build, created inside this copy.
  let status=run('npm',['run','build']);if(status)return status;
  if(mode==='build'){
   // Export only the sanitized API-mode public build for local serving checks.
   rmSync(path.join(root,'dist'),{recursive:true,force:true});
   cpSync(path.join(source,'dist'),path.join(root,'dist'),{recursive:true});
   return 0;
  }
  if(mode==='python'||mode==='all'){
   status=run(python,
    ['-m','pytest','-q','--tb=short']);
   if(status||mode==='python')return status;
  }
  return run(process.execPath,['--test',...readdirSync(path.join(source,'frontend/tests'))
   .filter(file=>file.endsWith('.test.js')).map(file=>'frontend/tests/'+file)]);
 }finally{rmSync(temp,{recursive:true,force:true})}
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{process.exitCode=runIsolated(process.argv[2]||'all')}
 catch{console.error('Isolated runner failed; no environment diagnostics are emitted.');process.exitCode=1}
}
