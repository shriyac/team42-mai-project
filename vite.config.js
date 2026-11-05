import {defineConfig} from 'vite';
import {fileURLToPath} from 'node:url';
const projectRoot=fileURLToPath(new URL('.',import.meta.url));
export default defineConfig({root:'frontend',build:{outDir:'../dist',emptyOutDir:true,rollupOptions:{input:{app:fileURLToPath(new URL('./frontend/index.html',import.meta.url)),apiDocs:fileURLToPath(new URL('./frontend/api-docs/index.html',import.meta.url))}}},server:{fs:{
 allow:[projectRoot,fileURLToPath(new URL('.',import.meta.resolve('@fontsource-variable/manrope')))],
 // Preserve Vite's default protections and deny local runtime material even
 // through /@fs/ URLs. Git ignore rules do not control HTTP file access.
 deny:['.env','.env.*','*.{crt,pem}','**/.git/**',
  ...['data','uploads','artifacts','.agents','.local','attached_assets','.streamlit'].map(dir=>`${projectRoot}${dir}/**`),
  '**/*.{sqlite,sqlite3,db}','**/*.sqlite*','**/rag_bindings*.json',`${projectRoot}documents.json`],
},host:'0.0.0.0',port:5174,strictPort:true,allowedHosts:['.replit.dev','.replit.app','localhost',process.env.REPLIT_DEV_DOMAIN].filter(Boolean),proxy:{'^/api(?:/|$)':{target:process.env.LAGA_API_PROXY||'http://127.0.0.1:8001',changeOrigin:true,cookieDomainRewrite:'',cookiePathRewrite:'/'}}}});
