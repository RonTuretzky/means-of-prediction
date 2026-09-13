import { abis } from '../contracts/gen';
import { BODY_PARSING } from '../config';
// Existing immutable markets keep the original tuple selector. Only fresh
// deployments encode the appended canonicalBody/offset/length fields.
function legacy(value: unknown): unknown {
  if (Array.isArray(value)) return value.filter(v => !v || typeof v !== 'object' || !['canonicalBody','bodyOffset','bodyLength'].includes((v as {name?:string}).name ?? '')).map(legacy);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,legacy(v)]));
  return value;
}
export const settlementAbi = (BODY_PARSING ? abis.HeadlineMarket : legacy(abis.HeadlineMarket)) as typeof abis.HeadlineMarket;
