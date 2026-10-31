import {reviewIsCurrent} from './compliance.js';
export function isPolicyDate(value){if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;const d=new Date(value+'T12:00:00Z');return !Number.isNaN(d.getTime())&&d.toISOString().slice(0,10)===value}
export const policyCategories={tenant:'Tenant policy',pets:'Pet policy',utilities:'Utilities usage',waste:'Waste management',community:'Community living',maintenance:'Maintenance',other:'Other policy'};
export function policyState(policy,asOf){if(asOf<policy.effectiveFrom)return 'scheduled';if(policy.effectiveTo&&asOf>=policy.effectiveTo)return 'expired';return 'active'}
export function resolvePolicies(versions,{asOf,propertyId=null,state=null,now=Date.now()}){
 if(!isPolicyDate(asOf))throw new Error('A policy reference date is required.');
 const applicable=versions.filter(v=>policyState(v,asOf)==='active'&&(!v.propertyId||v.propertyId===propertyId));
 const ids=new Set();for(const v of applicable){if(ids.has(v.familyId))throw new Error('Overlapping policy versions require administrator review.');ids.add(v.familyId)}
 const usable=v=>v.status==='ready'&&(!state||v.state===state)&&policyReviewCurrent(v,{asOf,now});
 return {eligible:applicable.filter(usable),unavailable:applicable.filter(v=>!usable(v))};
}
export function nextPolicyDate(versions,asOf){const latest=[...versions].sort((a,b)=>b.effectiveFrom.localeCompare(a.effectiveFrom))[0];if(!latest||latest.effectiveFrom<asOf)return asOf;const d=new Date(latest.effectiveFrom+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+1);return d.toISOString().slice(0,10)}

export function policyReviewCurrent(policy,{asOf,now=Date.now()}){return !!policy.state&&!!policy.contentHash&&policy.contentHash===policy.compliance?.contentHash&&reviewIsCurrent(policy.compliance,{state:policy.state,asOf,kind:'policy',scopeKey:policy.propertyId?'property:'+policy.propertyId:'state:'+policy.state,now})}
