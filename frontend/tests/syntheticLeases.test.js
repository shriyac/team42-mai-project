import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {inflateSync} from 'node:zlib';
import {tenants,leases,properties,leaseClauses} from '../src/data/fixtures.js';

const directory=new URL('../../docs/synthetic-leases/',import.meta.url);
const read=name=>fs.readFile(new URL(name,directory));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const manifest=JSON.parse(await read('manifest.json'));

test('synthetic lease corpus maps one packet to every mock tenant with matching amounts, dates and citation pages',async()=>{
 assert.equal(manifest.synthetic,true);
 assert.equal(manifest.documents.length,tenants.length);
 assert.equal(new Set(manifest.documents.map(d=>d.documentId)).size,10);
 assert.equal(new Set(manifest.documents.map(d=>d.tenantId)).size,10);
 for(const entry of manifest.documents){
  const record=JSON.parse(await read(entry.expectedExtraction));
  const tenant=tenants.find(t=>t.id===entry.tenantId),lease=leases.find(l=>l.id===entry.leaseId),property=properties.find(p=>p.id===entry.propertyId);
  assert.equal(tenant.name,entry.tenantName);assert.equal(lease.tenantId,tenant.id);assert.equal(lease.propertyId,property.id);
  assert.equal(record.documentId,lease.documents[0]);assert.equal(record.property.unit,lease.unit);
  assert.equal(record.property.address,property.address);assert.equal(record.state,property.state);
  assert.equal(record.terms.rentCents,lease.rent);assert.equal(record.terms.depositCents,lease.deposit);
  assert.equal(record.terms.startDate,lease.startDate);assert.equal(record.terms.endDate,lease.endDate);assert.equal(record.terms.noticeDays,lease.noticeDays);
  const anniversary=new Date(lease.startDate+'T12:00:00Z');anniversary.setUTCFullYear(anniversary.getUTCFullYear()+1);anniversary.setUTCDate(anniversary.getUTCDate()-1);
  assert.equal(anniversary.toISOString().slice(0,10),record.terms.endDate);
  const text=(await read(entry.text)).toString();
  assert.equal(sha(text),entry.textSha256);
  for(const clause of leaseClauses(lease)){
   const page=text.split('# Page '+clause.page+' / ')[1]?.split('\n---\n')[0];
   assert.ok(page?.includes(clause.quote),`${entry.text}: fixture clause on page ${clause.page}`);
  }
  for(const annexure of ['A','B','C','D'])assert.ok(text.includes('Annexure '+annexure+' /'));
  assert.ok(text.includes(record.specialConditions.text));
 }
});

test('synthetic household counts, pet fees and nonfunctional contact/banking fields are consistent',async()=>{
 let petHouseholds=0,childHouseholds=0,smokingHouseholds=0;
 for(const entry of manifest.documents){
  const record=JSON.parse(await read(entry.expectedExtraction)),h=record.household;
  assert.equal(h.totalMembers,h.members.length);assert.equal(h.children,h.members.filter(m=>m.age<18).length);assert.equal(h.adults,h.members.filter(m=>m.age>=18).length);
  assert.equal(h.members[0].name,record.tenant.name);assert.equal(h.ageAsOf,record.tenant.ageAsOf);assert.ok(record.tenant.age>=18);
  assert.ok(Number.isInteger(record.tenant.grossMonthlyIncomeCents)&&record.tenant.grossMonthlyIncomeCents>0);
  for(const phone of [record.tenant.phone,record.landlord.phone,record.emergencyContact.phone])assert.match(phone,/^202-555-01\d{2}$/);
  assert.match(record.banking.accountToken,/^TEST-ACCOUNT-\d{4}$/);assert.equal(record.banking.routingToken,'TEST-NOT-ROUTABLE');assert.equal(record.banking.automaticDebitAuthorized,false);
  assert.equal(record.signatureStatus,'unsigned_test_fixture');assert.equal(record.legalReviewStatus,'not_performed');
  assert.equal(record.terms.petFeeCents,record.pets.length?25000:0);
  for(const pet of record.pets){assert.ok(pet.approved);assert.ok(pet.weightPounds<=50)}
  if(record.pets.length)petHouseholds++;
  if(h.children)childHouseholds++;
  if(!record.tenant.smokingHabits.startsWith('Does not'))smokingHouseholds++;
 }
 assert.equal(petHouseholds,5);assert.equal(childHouseholds,5);assert.equal(smokingHouseholds,3);
});

test('checked-in PDFs have verified identity, twelve pages and text operators for ingestion',async()=>{
 for(const entry of manifest.documents){
  const bytes=await read(entry.pdf),raw=bytes.toString('latin1');
  assert.equal(bytes.subarray(0,5).toString(),'%PDF-');assert.equal(sha(bytes),entry.pdfSha256);assert.equal(bytes.length,entry.pdfBytes);
  assert.equal([...raw.matchAll(/\/Type\s*\/Page\b/g)].length,12);assert.equal(entry.pages,12);assert.equal(entry.layoutValidated,true);
  assert.ok(raw.includes('/ToUnicode'));assert.ok(raw.includes('/StructTreeRoot'));
  // Native text operators, rather than an image-only scan. Raster OCR is not needed.
  let hasText=false;
  for(const match of raw.matchAll(/stream\r?\n([\s\S]*?)\r?\nendstream/g)){
   try{const stream=inflateSync(Buffer.from(match[1],'latin1')).toString('latin1');if(/\bBT\b[\s\S]*?\b(?:Tj|TJ)\b/.test(stream))hasText=true}catch{/* Other PDF streams need not use FlateDecode. */}
  }
  assert.ok(hasText,entry.pdf+' must contain searchable text');
 }
});
