import {createMockGateway} from './mockGateway.js';
import {createHttpGateway} from './httpGateway.js';
const mode=import.meta.env?.VITE_LAGA_MODE||'mock';
if(!['mock','api'].includes(mode))throw new Error('VITE_LAGA_MODE must be mock or api.');
export const gateway=mode==='api'?createHttpGateway({base:import.meta.env.VITE_LAGA_API_BASE||'/api/v1'}):createMockGateway();
