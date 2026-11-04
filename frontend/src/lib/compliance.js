export const officialSources=[
 {title:'NC General Statutes · Chapter 42',description:'Landlord and tenant statutes',url:'https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/ByChapter/Chapter_42.html'},
 {title:'NC Department of Justice',description:'Renting a home · consumer guidance',url:'https://ncdoj.gov/protecting-consumers/home-repair-and-products/renting-a-home/'}
];
export function reviewIsCurrent(review,{state,asOf,kind,scopeKey,now=Date.now()}={}){
 const checked=Date.parse(review?.checkedAt),expires=Date.parse(review?.expiresAt);
 return review?.status==='passed'&&review.state===state&&review.asOf===asOf&&review.kind===kind&&review.scopeKey===scopeKey
  &&Number.isFinite(checked)&&Number.isFinite(expires)&&checked<=now&&now<expires
  &&/^[a-f0-9]{64}$/.test(review.lawRevision||'')&&/^[a-f0-9]{64}$/.test(review.contentHash||'')
  &&Array.isArray(review.citations)&&review.citations.length>0
  &&review.citations.every(c=>officialSources.some(s=>s.url===c.url)&&typeof c.section==='string'&&c.section.trim())
  &&(!review.findings||review.findings.length===0);
}
export async function answerReviewMatches(answer,request,{now=Date.now()}={}){
 if(!reviewIsCurrent(answer.compliance,{state:'NC',asOf:request.asOf,kind:'answer',scopeKey:request.scope.type+':'+(request.scope.id||'all'),now}))return false;
 // Bind a server review to exactly the text shown. The API must separately
 // enforce authorization and validate calculations before returning anything.
 const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(answer.answer));
 const hash=Array.from(new Uint8Array(bytes),byte=>byte.toString(16).padStart(2,'0')).join('');
 return hash===answer.compliance.contentHash;
}
export function reviewLabel(status){return {passed:'Review complete',conflict:'Changes required',unavailable:'Review unavailable',pending:'Awaiting legal review'}[status]||'Awaiting legal review'}
