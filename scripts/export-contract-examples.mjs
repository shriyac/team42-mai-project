import fs from 'node:fs/promises';
import {createMockGateway} from '../frontend/src/services/mockGateway.js';
const gateway=createMockGateway({delay:0});
const session=await gateway.login({role:'landlord'});
const workspace=await gateway.getWorkspace();
const leaseDetail=await gateway.getLease('lease-1');
const answer=await gateway.ask({question:'Can I bring a pet?',scope:{type:'lease',id:'lease-1'},asOf:workspace.asOf});
await fs.writeFile('contracts/examples.json',JSON.stringify({session:{data:session},workspace:{data:workspace},leaseDetail:{data:leaseDetail},answer:{data:answer},error:{error:{code:'VERSION_CONFLICT',message:'This policy changed. Refresh the library before adding a version.',requestId:'example-request-1',fields:{expectedVersion:'The current version is 3.'}}}},null,2)+'\n');
