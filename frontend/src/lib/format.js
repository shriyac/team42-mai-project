export const money=cents=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:cents%100?2:0,maximumFractionDigits:2}).format(cents/100);
export const date=value=>new Date(value.length===10?value+'T12:00:00':value).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
export const initials=name=>name.split(' ').map(s=>s[0]).slice(0,2).join('');
export const daysUntil=(end,asOf)=>Math.round((Date.parse(end+'T12:00:00Z')-Date.parse(asOf+'T12:00:00Z'))/86400000);
export function summarize(properties,leases,asOf){return {properties:properties.length,units:properties.reduce((s,p)=>s+p.units,0),occupied:leases.filter(l=>l.status==='active').length,monthlyRent:leases.filter(l=>l.status==='active').reduce((s,l)=>s+l.rent,0),outstandingRent:leases.filter(l=>l.paymentStatus==='due').reduce((s,l)=>s+l.rent,0),renewals:leases.filter(l=>daysUntil(l.endDate,asOf)>=0&&daysUntil(l.endDate,asOf)<=90).length}}
