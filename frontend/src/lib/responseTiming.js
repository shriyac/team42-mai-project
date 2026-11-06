// UI-only elapsed time: includes the full gateway request and response validation.
export async function askWithTiming(gateway,input,{now=()=>performance.now(),startedAt}={}){
 const started=startedAt??now();
 const answer=await gateway.ask(input);
 return {...answer,responseTimeMs:Math.max(0,now()-started)};
}
export function formatResponseTime(milliseconds){
 if(!Number.isFinite(milliseconds)||milliseconds<0)return null;
 return `Responded in ${(milliseconds/1000).toFixed(2)}s`;
}
