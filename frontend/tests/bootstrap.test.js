import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {landlord,tenants,properties,leases,policies,requests,leaseClauses} from '../src/data/fixtures.js';

test('Python bootstrap snapshot matches every fictional UI record and lease citation',async()=>{
 const data=JSON.parse(await fs.readFile(new URL('../../contracts/bootstrap.json',import.meta.url),'utf8'));
 assert.equal(data.synthetic,true);assert.equal(data.version,1);
 assert.deepEqual(data.users,[landlord,...tenants]);assert.deepEqual(data.properties,properties);
 assert.deepEqual(data.leases,leases.map(lease=>({lease,clauses:leaseClauses(lease)})));
 assert.deepEqual(data.policies,policies);assert.deepEqual(data.requests,requests);
 assert.equal(data.users.length,11);assert.equal(data.leases.length,10);assert.equal(data.policies.length,9);
});
