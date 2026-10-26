import { validateDraft, type RuleDraft } from '../../../services/rule-generator/src/schema.ts';

export type { RuleDraft };
export interface GenerationReceipt {
  provider: 'deepseek'; model: string; requestId: string; generatedAt: string;
  inputTokens: number; outputTokens: number;
}
export interface RuleGeneration { draft: RuleDraft; receipt: GenerationReceipt }
export interface FrozenDraft {
  version: 1; scope: 'local-planning-draft'; rules: RuleDraft; sha256: string;
  frozenAt: string; generatorReceipt: GenerationReceipt; editedAfterGeneration: boolean;
  alertsCreated: false; marketDeployed: false;
}

// The same serialization is used for the displayed commitment and exported plan.
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonicalJson).join(',') + ']';
  const record = value as Record<string, unknown>;
  return '{' + Object.keys(record).sort().map(k => JSON.stringify(k) + ':' + canonicalJson(record[k])).join(',') + '}';
}

export async function rulesHash(draft: RuleDraft): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonicalJson(draft)));
  return Array.from(new Uint8Array(digest), x => x.toString(16).padStart(2, '0')).join('');
}

export async function generateRules(apiUrl: string, accessToken: string, input: { question: string; context: string; deadline: string }): Promise<RuleGeneration> {
  const url = new URL(apiUrl);
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) {
    throw new Error('The rule service must use HTTPS.');
  }
  const response = await fetch(new URL('/v1/rules', url), {
    method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify(input), signal: AbortSignal.timeout(70000), credentials: 'omit', redirect: 'error',
  });
  const errors: Record<number, string> = {
    400: 'Check the question, deadline and source requirements, then try again.',
    401: 'The demo access code was not accepted.',
    403: 'This website is not allowed to use the rule service.',
    413: 'The request is too long. Shorten the source requirements.',
    429: 'The rule service is busy. Please wait a minute before trying again.',
    502: 'DeepSeek did not return a valid rule draft. No draft has been saved.',
    503: 'The rule service is not connected yet.',
    504: 'DeepSeek took too long to respond. No draft has been saved.',
  };
  if (!response.ok) throw new Error(errors[response.status] || 'Rule generation failed. No draft has been saved.');
  const raw = await response.text();
  if (raw.length > 100000) throw new Error('The rule service returned an oversized response.');
  const data: unknown = JSON.parse(raw);
  if (!data || typeof data !== 'object' || !('draft' in data) || !validateDraft(data.draft) || !('receipt' in data)) {
    throw new Error('The rule service returned an invalid draft.');
  }
  const receipt = data.receipt as GenerationReceipt;
  if (!receipt || receipt.provider !== 'deepseek' || typeof receipt.model !== 'string' || typeof receipt.requestId !== 'string' || !Number.isFinite(Date.parse(receipt.generatedAt)) || !Number.isFinite(receipt.inputTokens) || !Number.isFinite(receipt.outputTokens)) {
    throw new Error('The rule service returned an invalid generation receipt.');
  }
  if (data.draft.question !== input.question.trim() || Date.parse(data.draft.deadline) !== Date.parse(input.deadline)) {
    throw new Error('The generated question or deadline changed. No draft has been saved.');
  }
  return { draft: data.draft, receipt };
}

export function readSavedDraft(): FrozenDraft | null {
  try {
    const raw = localStorage.getItem('mop-rule-plan-v1');
    if (!raw || raw.length > 100000) return null;
    const item = JSON.parse(raw) as FrozenDraft;
    if (item.version !== 1 || item.scope !== 'local-planning-draft' || !validateDraft(item.rules) || !/^[a-f0-9]{64}$/.test(item.sha256) || item.alertsCreated !== false || item.marketDeployed !== false) return null;
    return item;
  } catch { return null; }
}
