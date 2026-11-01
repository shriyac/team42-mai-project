import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {landlord,tenants,properties,leases,leaseClauses} from '../frontend/src/data/fixtures.js';

const root=fileURLToPath(new URL('../',import.meta.url));
const directory=path.join(root,'docs/synthetic-leases');
const money=cents=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(cents/100);
const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const hash=value=>createHash('sha256').update(value).digest('hex');
const profiles=[
 {age:31,income:840000,occupation:'Product designer',members:[['Jordan Chen',33,'Adult household member'],['Riley Chen',6,'Child']],smoking:'Does not smoke or vape',pet:['Miso','Cat','Domestic shorthair',11],contact:['Taylor Chen','Sibling'],special:['Bike storage','One tagged bicycle may be stored in rack W-304. Keep corridor and stair landings clear. No separate bike-storage fee.']},
 {age:46,income:620000,occupation:'Library coordinator',members:[],smoking:'Smokes cigarettes outdoors only',pet:null,contact:['Morgan Wilson','Sibling'],special:['Ground-floor patio','Unit 101 includes patio P-101. Keep the access path clear; no permanent fixtures, grills or open flames. No separate patio charge.']},
 {age:29,income:780000,occupation:'Data analyst',members:[['Dev Patel',31,'Adult household member']],smoking:'Does not smoke or vape',pet:['Pippin','Dog','Beagle mix',28],contact:['Nisha Patel','Sibling'],special:['Reserved parking','Parking bay W-202 is assigned to this unit. Display the test permit. Visitors must use marked guest bays. Parking is included in base rent.']},
 {age:38,income:940000,occupation:'Construction estimator',members:[['Jamie Brooks',36,'Adult household member'],['Casey Brooks',9,'Child'],['Quinn Brooks',4,'Child']],smoking:'Does not smoke or vape',pet:null,contact:['Avery Brooks','Sibling'],special:['Balcony care','Unit 305 includes balcony B-305. Keep drains and exits clear. No structural alterations or storage of combustible materials. No separate balcony charge.']},
 {age:35,income:1020000,occupation:'Operations manager',members:[['Chidi Okafor',37,'Adult household member'],['Ada Okafor',7,'Child']],smoking:'Does not smoke or vape',pet:null,contact:['Ife Okafor','Sibling'],special:['Roof terrace access','Unit 2A receives two terrace access cards. Shared quiet hours apply; no exclusive terrace use is granted. Access is included in base rent.']},
 {age:27,income:710000,occupation:'Software tester',members:[['Sam Rivera',26,'Adult household member']],smoking:'Vapes outdoors only',pet:['Luna','Dog','Terrier mix',19],contact:['Alexis Rivera','Sibling'],special:['Guest parking','For Unit 3B, one overnight guest permit may be requested through the portal, subject to marked-space availability. No guaranteed guest space or additional charge is created by this annexure.']},
 {age:42,income:980000,occupation:'Project coordinator',members:[['Elena Rossi',14,'Child']],smoking:'Does not smoke or vape',pet:null,contact:['Marco Rossi','Sibling'],special:['Assigned storage','Storage locker J-4A is assigned to this unit. Store ordinary household items only; no fuel, chemicals or food. Storage is included in base rent.']},
 {age:24,income:590000,occupation:'Technical support specialist',members:[],smoking:'Does not smoke or vape',pet:['Bean','Cat','Domestic longhair',9],contact:['Min Kim','Sibling'],special:['Garden equipment','Unit 1 may use the shared garden tool cabinet after orientation. Return tools clean and do not store them in common walkways. No separate garden fee.']},
 {age:33,income:800000,occupation:'Account coordinator',members:[['Drew Thompson',34,'Adult household member'],['Emery Thompson',5,'Child']],smoking:'Smokes cigarettes outdoors only',pet:['Scout','Dog','Spaniel mix',32],contact:['Robin Thompson','Sibling'],special:['Laundry access','Unit 2 receives laundry access token C-2. Follow posted machine instructions and remove belongings promptly. Machine charges, if any, are outside this sample lease; no numeric charge is specified.']},
 {age:52,income:880000,occupation:'Logistics planner',members:[['Harper Bennett',50,'Adult household member']],smoking:'Does not smoke or vape',pet:null,contact:['Cameron Bennett','Sibling'],special:['Move-in condition record','Unit 3 has a recorded cosmetic scratch on the kitchen cabinet and a scuff near the entry. These are pre-existing sample observations, not tenant-caused damage. No repair charge is agreed by this annexure.']}
];
await fs.mkdir(directory,{recursive:true});
const manifest={datasetVersion:'1.0.0',synthetic:true,createdOn:'2026-10-31',currency:'USD',source:'frontend/src/data/fixtures.js',documents:[]};
for(const [index,lease] of leases.entries()){
 const profile=profiles[index],tenant=tenants.find(t=>t.id===lease.tenantId),property=properties.find(p=>p.id===lease.propertyId);
 const execution=new Date(lease.startDate+'T12:00:00Z');execution.setUTCDate(execution.getUTCDate()-7);
 const signedOn=execution.toISOString().slice(0,10),n=index+1,stem=`lease-${String(n).padStart(2,'0')}-${tenant.name.toLowerCase().replaceAll(' ','-')}`;
 const household=[{name:tenant.name,age:profile.age,relationship:'Named tenant'},...profile.members.map(([name,age,relationship])=>({name,age,relationship}))];
 const pet=profile.pet?{name:profile.pet[0],species:profile.pet[1],breed:profile.pet[2],weightPounds:profile.pet[3],approved:true,approvalDate:signedOn,oneTimeFeeCents:25000}:null;
 const record={synthetic:true,datasetVersion:manifest.datasetVersion,documentId:lease.documents[0],leaseId:lease.id,tenantId:tenant.id,propertyId:property.id,state:property.state,
  landlord:{name:landlord.name,organization:landlord.organization,email:landlord.email,phone:'202-555-0100'},
  tenant:{name:tenant.name,email:tenant.email,phone:`202-555-${String(101+n).padStart(4,'0')}`,age:profile.age,ageAsOf:signedOn,occupation:profile.occupation,grossMonthlyIncomeCents:profile.income,smokingHabits:profile.smoking},
  property:{name:property.name,address:property.address,city:property.city,state:property.state,unit:lease.unit},
  household:{members:household,totalMembers:household.length,children:household.filter(m=>m.age<18).length,adults:household.filter(m=>m.age>=18).length,ageAsOf:signedOn},
  emergencyContact:{name:profile.contact[0],relationship:profile.contact[1],phone:`202-555-${String(151+n).padStart(4,'0')}`},
  banking:{bankName:'TEST ONLY Community Bank (fictional)',accountHolder:tenant.name,accountType:'Checking',accountToken:`TEST-ACCOUNT-${String(n).padStart(4,'0')}`,routingToken:'TEST-NOT-ROUTABLE',accountDisplay:`**** TEST${String(n).padStart(2,'0')}`,automaticDebitAuthorized:false},
  terms:{executionDate:signedOn,startDate:lease.startDate,endDate:lease.endDate,durationMonths:12,endDateInclusive:true,rentCents:lease.rent,depositCents:lease.deposit,currency:lease.currency,dueDay:lease.dueDay,lateFeeCents:5000,lateFeeAfterDay:5,noticeDays:lease.noticeDays,petFeeCents:pet?25000:0},
  pets:pet?[pet]:[],specialConditions:{title:profile.special[0],text:profile.special[1]},
  signatureStatus:'unsigned_test_fixture',legalReviewStatus:'not_performed',pages:[]};
 const acknowledgment='Tenant signature: ____________________  Date: __________\nLandlord signature: __________________  Date: __________\nUnsigned test fixture. Do not execute or use for a real tenancy.';
 const clause=leaseClauses(lease);
 const pages=[
  ['Residential lease / agreement particulars',[
   'SYNTHETIC TEST DOCUMENT — NOT FOR SIGNATURE OR LEGAL USE. Every identity, address, household detail, amount and financial/contact detail in this packet is fictional. No statutory compliance review has been performed.',
   `Document ID: ${record.documentId}\nLease ID: ${lease.id}\nTenant ID: ${tenant.id}\nProperty ID: ${property.id}\nState: North Carolina (NC)`,
   `Landlord: ${landlord.name}, for ${landlord.organization}\nTenant: ${tenant.name}\nPremises: ${property.name}, ${property.address}, Unit ${lease.unit}, ${property.city}`,
   `Agreement date: ${signedOn}\nCommencement: ${lease.startDate}\nEnd date (inclusive): ${lease.endDate}\nLease duration: 12 calendar months\nMonthly rent: ${money(lease.rent)}\nSecurity deposit: ${money(lease.deposit)}`,
   'This is a fixed-term fictional residential lease packet for backend extraction and retrieval testing. The agreement date is a synthetic scenario date, not evidence that anyone signed. Currency is USD. No real account is connected.',
   'Packet map: household p. 2; rent and banking p. 3; deposit p. 4; utilities p. 5; occupancy p. 6; maintenance p. 7; pet annexure A p. 8; smoking annexure B p. 9; waste annexure C p. 10; unit annexure D p. 11; renewal and signatures p. 12.'
  ]],
  ['Household and tenant information',[
   `2.1 Named tenant: ${tenant.name}\nAge: ${profile.age} years as of ${signedOn}\nOccupation (synthetic): ${profile.occupation}\nGross monthly personal income: ${money(profile.income)}\nGross annual personal income: ${money(profile.income*12)}\nTenant email: ${tenant.email}\nTenant telephone: ${record.tenant.phone}`,
   `2.2 Total household members: ${household.length}\nAdults (18 or older): ${record.household.adults}\nChildren (under 18): ${record.household.children}\nAll ages are measured as of ${signedOn}. The named tenant is included in the household count.`,
   ...household.map((m,i)=>`Household member ${i+1}: ${m.name}; age ${m.age}; ${m.relationship}.`),
   'Only the named tenant is a lease signatory in this test scenario. Other adults are listed occupants, not automatically co-tenants or guarantors. Children have no signature lines. Income and ages are synthetic extraction fields, not eligibility criteria, occupancy limits or grounds for different fees.',
   `2.3 Emergency contact: ${record.emergencyContact.name}\nRelationship: ${record.emergencyContact.relationship}\nEmergency contact telephone: ${record.emergencyContact.phone}\nContact is not a guarantor and has no payment obligation.`
  ]],
  ['Rent, payment and banking instructions',[
   `3.1 ${clause[0].quote}`,
   `3.2 Base monthly rent: ${money(lease.rent)}\nDue day: 1\nGrace period through day: 5\nFlat late fee after day 5: ${money(5000)}\nExample payment on day 6: ${money(lease.rent+5000)} = ${money(lease.rent)} + ${money(5000)}. This is arithmetic on fictional contract terms, not a lawful-fee determination or an account balance.`,
   `3.3 Payment method: manual bank-transfer test workflow.\nFictional bank: ${record.banking.bankName}\nAccount holder: ${tenant.name}\nAccount type: ${record.banking.accountType}\nAccount display: ${record.banking.accountDisplay}\nAccount token: ${record.banking.accountToken}\nRouting token: ${record.banking.routingToken}`,
   'These tokens are deliberately nonfunctional. No actual account number, routing number, card number or online-banking credential is provided. This lease is not an ACH or automatic debit authorization; no payment should be attempted.',
   '3.4 Rent excludes any one-time pet fee stated in annexure A. Water and ordinary shared waste service are included. There is no percentage late fee or daily compounding in this sample. Partial-month proration and current balances are not specified; do not infer them.'
  ]],
  ['Security deposit and condition record',[
   `4.1 Deposit amount: ${money(lease.deposit)}. Deposit is separate from monthly rent. This packet does not assert that any transfer has occurred.`,
   `4.2 ${clause[1].quote}`,
   '4.3 Pet-related damage refers back to section 4.2; the pet fee does not erase responsibility for documented damage. No automatic forfeiture or guaranteed deduction is established by this test packet.',
   `4.4 Move-in condition: ${index===9?profile.special[1]:'Sample baseline condition is recorded as clean and habitable, with no itemized pre-existing defect supplied in this scenario. This is fictional narrative, not an inspection report.'}`,
   '4.5 A move-out comparison should distinguish ordinary wear from documented new damage. Deposit custody, accounting deadlines, interest and statutory rights are not determined by this synthetic document. No legal conclusion may be inferred from missing text.',
   acknowledgment
  ]],
  ['Utilities and service responsibilities',[
   '5.1 Tenant arranges and pays for electricity and internet. Water is included in base rent. Ordinary shared trash and recycling service is included. No separate monthly utility allocation or usage formula is specified.',
   '5.2 Report leaks promptly through the resident portal. If an issue creates an immediate threat to safety, contact appropriate emergency services first and then notify management. No synthetic contact in this packet is a real service.',
   '5.3 Keep access to meters, service panels and drains unobstructed. Do not modify plumbing, electrical wiring or fixed appliances without written permission. Maintenance requests follow section 7.',
   '5.4 These are lease-specific test terms. This packet does not silently incorporate later revisions of organization-wide policies. The policy library has separate effective dates and versions; test retrieval of those documents independently.',
   '5.5 No internet speed, service provider, electricity tariff or outage compensation is promised. An absent numeric rate must be extracted as unspecified, rather than zero.'
  ]],
  ['Occupancy, shared areas and access',[
   `6.1 The household roster in section 2 contains ${household.length} people, including ${record.household.children} children. The roster documents this scenario; it does not establish a maximum lawful occupancy. Notify management of proposed changes for a separate review.`,
   '6.2 The premises are used as the named household’s home. No right to sublet or transfer this fictional agreement is supplied. Request written clarification before assuming permission for a different use.',
   '6.3 Quiet hours are 10 p.m. to 8 a.m. Keep corridors, exits and stairways clear. Leave common rooms ready for the next resident. These common-area terms apply to all listed households.',
   '6.4 Management access and inspection scheduling require separate coordination. This packet supplies no emergency-entry test or statutory notice period and creates no claim about legal entry rights.',
   '6.5 Household ages, children, income and smoking disclosures are included solely to exercise parsers. They do not vary rent, deposit, notice periods or access to common amenities in this corpus.'
  ]],
  ['Maintenance, safety and contacts',[
   '7.1 Submit routine maintenance requests through the resident portal. Describe the location, issue and safe access window. No response-time service-level agreement is specified.',
   `7.2 Fictional management contact: ${landlord.name}, ${landlord.organization}\nEmail: ${landlord.email}\nTest telephone: 202-555-0100\nHousehold emergency contact: ${record.emergencyContact.name}, ${record.emergencyContact.phone}.`,
   '7.3 For an immediate threat to safety, use appropriate real emergency services rather than these fictional contacts. Do not use a maintenance request or the household emergency contact as a substitute for emergency services.',
   '7.4 Report water leaks, damaged locks, smoke-alarm concerns and electrical hazards promptly. Do not undertake unsafe repairs. This packet is not an inspection certificate or safety manual.',
   '7.5 No Social Security number, birth date, government ID, medical information, live credential or usable payment instrument is part of this dataset. Store and process this corpus as synthetic test content.'
  ]],
  ['Annexure A / pets and responsibilities',[
   `8.1 ${clause[2].quote}`,
   pet?`8.2 Approved pet: ${pet.name}\nSpecies: ${pet.species}\nBreed/description: ${pet.breed}\nWeight: ${pet.weightPounds} pounds\nApproval date (scenario): ${signedOn}\nOne-time pet fee: ${money(pet.oneTimeFeeCents)}\nMonthly pet rent: not specified.`:'8.2 No pet is registered or approved for this household at execution. Pet count: 0. Current pet fee obligation: $0.00. The conditional $250 fee in section 8.1 is not a charge due for a household with no approved pet.',
   '8.3 Clean up pet waste immediately. Keep an approved pet leashed in shared areas. Prevent nuisance and document damage using section 4.2. Any later pet request requires its own recorded approval; do not infer approval from a general policy.',
   '8.4 This annexure describes ordinary pets only. It does not classify assistance animals, decide accommodation requests or determine whether a fee is legally permitted. Those questions require a separate review.',
   `Annexure A applies to ${lease.id}, ${property.name}, Unit ${lease.unit}.\n${acknowledgment}`
  ]],
  ['Annexure B / smoking and vaping',[
   `9.1 Named tenant disclosure: ${profile.smoking}. This is a fictional self-report as of ${signedOn}, not evidence about every occupant or a health assessment.`,
   '9.2 In this test agreement, no smoking or vaping occurs inside the unit or enclosed shared areas. Any smoking or vaping is limited to an outdoor designated area identified by management. Dispose of smoking materials safely; do not leave them in landscaping or household recycling.',
   '9.3 No smoking-related fee, rent surcharge or additional deposit is specified. Do not infer a zero damage claim or a penalty schedule. Any observed damage is evaluated under section 4.2.',
   '9.4 Disclosure does not create an exception to the indoor rule. This annexure records the scenario without making a legal, medical or insurance determination.',
   `Annexure B applies to ${lease.id}, ${property.name}, Unit ${lease.unit}.\n${acknowledgment}`
  ]],
  ['Annexure C / waste, recycling and shared spaces',[
   '10.1 Place ordinary household waste in tied bags in the designated bins. Separate clean recyclables into marked containers. Keep lids and access paths clear.',
   '10.2 Do not leave bulky items in the waste room. Arrange collection with management before disposing of furniture or large packaging. Hazardous materials and electronic waste require separate instructions; no collection schedule or price is supplied here.',
   '10.3 Clean up spills and pet waste promptly. Do not store waste in hallways, stairwells or balconies. Quiet hours remain 10 p.m. to 8 a.m. when moving items through shared spaces.',
   '10.4 Ordinary shared waste service is included in base rent. No bulk-item fee, contamination fee or fine amount is specified in this packet. Do not invent one during extraction.',
   `Annexure C applies to ${lease.id}, ${property.name}, Unit ${lease.unit}.\n${acknowledgment}`
  ]],
  ['Annexure D / unit-specific conditions',[
   `11.1 ${profile.special[0]}\n${profile.special[1]}`,
   `11.2 This condition is specific to ${property.name}, Unit ${lease.unit}, ${lease.id}. It must not be attached to any other unit during ingestion, retrieval or answer generation.`,
   '11.3 This annexure does not modify base rent, security deposit, approved household count, the conditional pet fee or the fixed term. Any unspecified charge remains unspecified.',
   '11.4 Document hierarchy for this test fixture: agreement sections control general terms; the annexures provide the stated pet, smoking, waste and unit details. An apparent contradiction requires clarification, not an invented rule. No later policy version automatically amends this signed-date scenario.',
   `Separate acknowledgment requested for the unit condition above.\n${acknowledgment}`
  ]],
  ['Renewal, notice and signature schedule',[
   `12.1 ${clause[3].quote}`,
   `12.2 Fixed term: ${lease.startDate} through ${lease.endDate}, inclusive; 12 calendar months. Notice period in this fictional contract: ${lease.noticeDays} days. No automatic renewal rent or month-to-month conversion is specified.`,
   '12.3 Attachments: Annexure A (pets, p. 8); Annexure B (smoking/vaping, p. 9); Annexure C (waste/recycling, p. 10); Annexure D (unit conditions, p. 11). Each has a separate unsigned acknowledgment block.',
   `12.4 Named tenant: ${tenant.name}\nLandlord representative: ${landlord.name}, ${landlord.organization}\nScenario agreement date: ${signedOn}\nSignature status: UNSIGNED TEST FIXTURE.`,
   acknowledgment,
   'Dataset notice: this corpus is for software ingestion, retrieval, calculation and isolation testing only. It is not an enforceable lease form, legal advice, a government mandate or a legal compliance certification. It must not be used to establish rights or obligations of real people.'
  ]]
 ];
 record.pages=pages.map(([title],i)=>({page:i+1,title}));
 const text=pages.map(([title,paragraphs],i)=>`# Page ${i+1} / ${title}\n\nSYNTHETIC TEST DOCUMENT | ${lease.id} | ${tenant.name} | Unit ${lease.unit}\n\n${paragraphs.join('\n\n')}\n`).join('\n---\n\n');
 const html=`<!doctype html><html lang="en"><head><meta charset="UTF-8"><title>${esc(tenant.name)} / synthetic lease</title><style>@page{size:Letter;margin:0}*{box-sizing:border-box}body{margin:0;color:#25324a;font:11pt/1.5 Arial,sans-serif}.page{width:8.5in;height:11in;padding:.56in .66in .6in;position:relative;break-after:page;overflow:hidden}.page:last-child{break-after:auto}header{display:flex;justify-content:space-between;border-bottom:2px solid #6955a5;padding-bottom:12px;color:#6955a5;font-size:9pt}header b{font-size:19pt}h1{font-size:23pt;line-height:1.18;margin:24px 0 18px}p{white-space:pre-line;margin:0 0 15px}p:first-of-type{border-left:3px solid #b3a2db;padding-left:12px}footer{position:absolute;bottom:.32in;left:.66in;right:.66in;border-top:1px solid #ddd6e9;padding-top:8px;display:flex;justify-content:space-between;font-size:8pt;color:#626c80}.content{max-height:8.8in}</style></head><body>${pages.map(([title,paragraphs],i)=>`<section class="page"><header><b>laga.</b><span>FICTIONAL LEASE / TEST DATA ONLY</span></header><div class="content"><h1>${esc(title)}</h1>${paragraphs.map(p=>`<p>${esc(p)}</p>`).join('')}</div><footer><span>${esc(tenant.name)} / ${lease.id} / Unit ${esc(lease.unit)}</span><span>${i+1} / ${pages.length}</span></footer></section>`).join('')}</body></html>`;
 await fs.writeFile(path.join(directory,stem+'.json'),JSON.stringify(record,null,2)+'\n');
 await fs.writeFile(path.join(directory,stem+'.md'),text);
 await fs.writeFile(path.join(directory,stem+'.html'),html);
 manifest.documents.push({documentId:record.documentId,leaseId:lease.id,tenantId:tenant.id,propertyId:property.id,tenantName:tenant.name,unit:lease.unit,state:'NC',pdf:stem+'.pdf',text:stem+'.md',expectedExtraction:stem+'.json',html:stem+'.html',pages:pages.length,textSha256:hash(text)});
}
await fs.writeFile(path.join(directory,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
console.log(`Generated ${manifest.documents.length} synthetic lease packets. Run node scripts/print-synthetic-leases.mjs to create PDFs.`);
