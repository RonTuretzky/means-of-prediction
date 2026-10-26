import { afterEach, describe, expect, it, vi } from 'vitest';
import worker from '../src/index';
import { validateDraft, validateRuleRequest, SOURCE_WARNING } from '../src/schema';
import { PROVIDER_URL } from '../src/limits';

const token = 'test-access-token-with-at-least-32-characters';
const input = { question: 'Will the 2027 Nobel Peace Prize name an individual laureate?', context: 'Use the official announcement.', deadline: '2027-12-31T23:59:00.000Z' };
const draft = {
  question: input.question, eventDefinition: 'The 2027 Nobel Peace Prize award announcement.',
  yesConditions: ['An individual is named as a laureate.'], noConditions: [], abstainConditions: ['The event time is not established.'],
  deadline: input.deadline, evidenceRequirements: ['Complete Google signature and qualifying result block.'],
  allowedSources: [{ name: 'Nobel Prize', host: 'nobelprize.org', role: 'Official result' }],
  alertQueries: [{ query: '2027 Nobel Peace Prize laureate', job: 'Find the result.' }],
  judgeInstructions: 'Abstain without positive evidence. Query text is not proof.', warnings: ['Review the proposed sources.'],
};
const providerResponse = () => ({ id: 'fixture-request-id', model: 'deepseek-flash',
  choices: [{ finish_reason: 'stop', message: { role: 'assistant', content: JSON.stringify(draft) } }],
  usage: { prompt_tokens: 100, completion_tokens: 200 },
});
const settings = (): Env => ({
  DEEPSEEK_API_KEY: 'test-fake-provider-key', RULE_GENERATOR_TOKEN: token, DEEPSEEK_MODEL: 'deepseek-flash',
  ALLOWED_ORIGINS: 'https://ronturetzky.github.io,http://127.0.0.1:5201',
  RULES_RATE_LIMITER: { limit: async () => ({ success: true }) },
});
function request(body: unknown = input, headers: Record<string, string> = {}) {
  return new Request('https://rules.test/v1/rules', { method: 'POST', body: JSON.stringify(body),
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, Origin: 'https://ronturetzky.github.io', ...headers } });
}
afterEach(() => vi.restoreAllMocks());

describe('rule API in the Workers runtime', () => {
  it('authenticates and preserves the exact event fields, returning only a validated draft and receipt', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
      expect(url).toBe(PROVIDER_URL);
      expect(init?.redirect).toBe('manual');
      const body = JSON.parse(init?.body as string);
      expect(body.model).toBe('deepseek-flash'); expect(body.max_tokens).toBe(2500);
      expect(body.thinking).toEqual({ type: 'disabled' }); expect(body.tools).toBeUndefined();
      return Response.json(providerResponse());
    });
    const res = await worker.fetch(request(), settings());
    expect(res.status).toBe(200); expect(fetcher).toHaveBeenCalledTimes(1);
    const result = await res.json() as { draft: unknown; receipt: { provider: string } };
    expect(result.draft).toEqual(draft); expect(result.receipt.provider).toBe('deepseek');
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe('https://ronturetzky.github.io');
    expect(res.headers.get('Cache-Control')).toBe('no-store');
  });

  it('fails closed for wrong tokens, missing secret configuration, disallowed origins and unavailable limits', async () => {
    const upstream = vi.spyOn(globalThis, 'fetch');
    expect((await worker.fetch(request(input, { Authorization: 'Bearer wrong' }), settings())).status).toBe(401);
    expect((await worker.fetch(request(), { ...settings(), DEEPSEEK_API_KEY: '' })).status).toBe(503);
    expect((await worker.fetch(request(input, { Origin: 'https://untrusted.example' }), settings())).status).toBe(403);
    expect((await worker.fetch(request(), { ...settings(), RULES_RATE_LIMITER: { limit: async () => { throw Error('offline'); } } })).status).toBe(503);
    expect(upstream).not.toHaveBeenCalled();
  });

  it('enforces rate and payload limits before the paid API call', async () => {
    const upstream = vi.spyOn(globalThis, 'fetch');
    const limited = await worker.fetch(request(), { ...settings(), RULES_RATE_LIMITER: { limit: async () => ({ success: false }) } });
    expect(limited.status).toBe(429); expect(limited.headers.get('Retry-After')).toBe('60');
    expect((await worker.fetch(request({ ...input, context: 'x'.repeat(25000) }), settings())).status).toBe(413);
    expect((await worker.fetch(request({ ...input, context: 'DKIM-Signature: private-mail' }), settings())).status).toBe(400);
    expect(upstream).not.toHaveBeenCalled();
  });

  it('rejects truncated, malformed, altered and oversized provider outputs and hides provider diagnostics', async () => {
    const responses = [
      new Response('provider secret details', { status: 401 }),
      Response.json({ ...providerResponse(), choices: [{ finish_reason: 'length', message: { role: 'assistant', content: JSON.stringify(draft) } }] }),
      Response.json({ ...providerResponse(), choices: [{ finish_reason: 'stop', message: { role: 'assistant', content: JSON.stringify({ ...draft, deadline: '2028-01-01T00:00:00Z' }) } }] }),
      Response.json({ ...providerResponse(), choices: [{ finish_reason: 'stop', message: { role: 'assistant', content: 'garbage' } }] }),
      new Response('x'.repeat(66000), { headers: { 'Content-Type': 'application/json' } }),
    ];
    for (const upstream of responses) {
      const mock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(upstream);
      const res = await worker.fetch(request(), settings());
      expect(res.status).toBe(502); expect(await res.text()).not.toContain('provider secret details');
      mock.mockRestore();
    }
  });

  it('allows exact preflights and denies unrelated methods/routes', async () => {
    const res = await worker.fetch(new Request('https://rules.test/v1/rules', { method: 'OPTIONS', headers: {
      Origin: 'http://127.0.0.1:5201', 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'authorization,content-type',
    } }), settings());
    expect(res.status).toBe(204); expect(res.headers.get('Access-Control-Allow-Origin')).toBe('http://127.0.0.1:5201');
    expect((await worker.fetch(new Request('https://rules.test/v1/rules'), settings())).status).toBe(405);
    expect((await worker.fetch(new Request('https://rules.test/arbitrary'), settings())).status).toBe(404);
  });
});

it('rejects impossible dates, unknown fields, URL hosts and missing-source ambiguity without the required warning', () => {
  expect(validateRuleRequest({ ...input, deadline: '2027-02-30T00:00:00Z' }).ok).toBe(false);
  expect(validateRuleRequest({ ...input, arbitrary: 'execute' }).ok).toBe(false);
  expect(validateDraft({ ...draft, allowedSources: [{ name: 'Bad', host: 'https://nobelprize.org', role: 'Official' }] })).toBe(false);
  expect(validateDraft({ ...draft, allowedSources: [] })).toBe(false);
  expect(validateDraft({ ...draft, allowedSources: [], warnings: [SOURCE_WARNING] })).toBe(true);
});
