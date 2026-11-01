// Public build-time feature flag; enable only with the exact value true.
export const stateVerificationEnabled=import.meta.env?.VITE_LAGA_STATE_VERIFICATION==='true';
