import {defineConfig} from 'vite';
import {fileURLToPath} from 'node:url';
export default defineConfig({root:'frontend',build:{outDir:'../dist',emptyOutDir:true,rollupOptions:{input:{app:fileURLToPath(new URL('./frontend/index.html',import.meta.url)),apiDocs:fileURLToPath(new URL('./frontend/api-docs/index.html',import.meta.url))}}},server:{host:'0.0.0.0',port:5174,strictPort:true,allowedHosts:['.replit.dev','.replit.app','localhost'],proxy:{'^/api(?:/|$)':{target:process.env.LAGA_API_PROXY||'http://127.0.0.1:8001',changeOrigin:true,cookieDomainRewrite:'',cookiePathRewrite:'/'}}}});
