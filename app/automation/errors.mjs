// Provider exceptions may contain credentials, email bodies, or RPC calldata.
export class ServiceError extends Error {
  constructor(code, status = 503) { super(code); this.code = code; this.status = status; }
}
export const fail = (code, status) => { throw new ServiceError(code, status); };
export const safeCode = error => error instanceof ServiceError ? error.code : 'service_unavailable';
