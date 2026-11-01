// Regenerate the Python bootstrap snapshot when fictional UI fixtures change.
import fs from 'node:fs/promises';
import {landlord,tenants,properties,leases,policies,requests,leaseClauses} from '../frontend/src/data/fixtures.js';
const fixture={version:1,synthetic:true,organizationId:'org-alder-demo',users:[landlord,...tenants],properties,
 leases:leases.map(lease=>({lease,clauses:leaseClauses(lease)})),policies,requests};
await fs.writeFile(new URL('../contracts/bootstrap.json',import.meta.url),JSON.stringify(fixture,null,2)+'\n');
console.log('Exported deterministic fictional bootstrap snapshot.');
