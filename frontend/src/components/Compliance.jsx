import {stateVerificationEnabled} from '../lib/features.js';
import React from 'react';
import {ArrowUpRight,BookOpen,Check,Clock3,MapPin,ShieldCheck} from 'lucide-react';
import {Badge} from './ui.jsx';
import {policyReviewCurrent} from '../lib/policies.js';
import {officialSources,reviewLabel} from '../lib/compliance.js';

export function JurisdictionCard({demo=false,compact=false,state='NC',documents=[]}){
 if(!stateVerificationEnabled)return null;
 const pending=documents.filter(p=>p.compliance?.status!=='passed').length;
 return <section className={'jurisdiction-card '+(compact?'compact':'')} aria-label="State law and review status">
  <div className="jurisdiction-heading"><span className="jurisdiction-icon"><ShieldCheck size={23}/></span><div><span className="eyebrow">STATE LAW & YOUR DOCUMENTS</span><h2>{state==='NC'?'North Carolina':state||'Property state required'}</h2></div><span className="state-mark" aria-hidden="true">{state||'—'}</span></div>
  <p>{compact?'Your lease determines the state. No extra details needed.':'Each policy belongs to a state. Its rules need a legal review before they can support lease guidance.'}</p>
  <div className="jurisdiction-facts"><span><MapPin size={14}/>Property jurisdiction</span><Badge tone="lavender">{state||'Missing'}</Badge></div>
  <div className="jurisdiction-facts"><span><Clock3 size={14}/>Legal review</span><Badge tone="amber">{demo?'Unavailable in preview':pending?`${pending} pending`:'See document reviews'}</Badge></div>
  <details className="government-sources"><summary><BookOpen size={15}/>Official NC references<span>2 sources</span></summary><div>{officialSources.map(source=><a key={source.url} href={source.url} target="_blank" rel="noreferrer"><span><strong>{source.title}</strong><small>{source.description}</small></span><ArrowUpRight size={16}/><span className="sr-only"> (opens in a new tab)</span></a>)}</div><p>Reference links are available now. Automated checks require the review service.</p></details>
 </section>
}

export function ReviewDetails({policy,demo,asOf}){
 const ingested=policy.status==='ready',passed=policyReviewCurrent(policy,{asOf});
 const steps=[{title:'State assigned',detail:policy.state==='NC'?'North Carolina · NC':'Property state is missing',done:policy.state==='NC'},
  {title:'Document processed',detail:ingested?'Text available for retrieval':demo?'Upload metadata saved; PDF processing is not connected.':'Waiting for document processing.',done:ingested},
  {title:'Rules checked against state law',detail:passed?'Review recorded for this version.':policy.compliance?.status==='conflict'?'Conflicting rules need changes before use.':'A legal review is required before this policy can support an answer.',done:passed},
  {title:'Available to the assistant',detail:passed&&ingested?'Subject to the selected date and property.':'Withheld until processing and legal review complete.',done:passed&&ingested}];
 return <div className="review-details"><div className="review-summary"><span className="jurisdiction-icon"><ShieldCheck size={24}/></span><div><strong>{reviewLabel(policy.compliance?.status==='passed'&&!passed?'unavailable':policy.compliance?.status)}</strong><p>{policy.title} · Version {policy.version} · {policy.state||'State missing'}</p></div></div><ol className="review-steps">{steps.map((step,i)=><li key={step.title} className={step.done?'done':''}><span className="step-marker">{step.done?<Check size={14}/>:i+1}</span><div><strong>{step.title}</strong><p>{step.detail}</p></div></li>)}</ol>{policy.compliance?.findings?.length>0&&<div className="review-findings"><h3>Items to resolve</h3>{policy.compliance.findings.map((f,i)=><p key={i}>{f.message||f.description||'Review this clause with the property manager.'}</p>)}</div>}<p className="review-footnote">A state tag identifies the jurisdiction. It does not certify that the document complies with the law.</p></div>
}
