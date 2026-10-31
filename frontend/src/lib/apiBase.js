export function normalizeApiBase(value){
 const base=String(value||'').trim().replace(/\/+$/,'');
 if(base.startsWith('/')&&!base.startsWith('//')&&!/[?#\\\s]/.test(base))return base;
 let url;try{url=new URL(base)}catch{throw new Error('Use a path such as /api/v1 or a full HTTP(S) URL ending in /api/v1.')}
 if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash)throw new Error('Use an HTTP(S) API URL without credentials, query parameters or fragments.');
 return url.toString().replace(/\/+$/,'');
}
