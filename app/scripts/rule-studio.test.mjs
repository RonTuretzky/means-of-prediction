import test from 'node:test';
import assert from 'node:assert/strict';
import { canonicalJson, generateRules, rulesHash, readSavedDraft } from '../src/lib/rule-studio.ts';

const draft = {
  question: 'Will the official result name an individual winner?', eventDefinition: 'The named 2027 award event.',
  yesConditions: ['An official result names an individual laureate.'], noConditions: [],
  abstainConditions: ['The excerpt does not establish the actual event date or named laureate.'],
  deadline: '2027-12-31T23:59:00.000Z', evidenceRequirements: ['Explicit event, year and laureate in the result text.'],
  allowedSources: [{ name: 'Nobel Committee', host: 'nobelprize.org', role: 'Official result' }],
  alertQueries: [{ query: 'site:nobelprize.org "2027" "laureate"', job: 'Find the official result.' }],
  judgeInstructions: 'Abstain on missing evidence; query text and delivery date do not prove an event.',
  warnings: ['A Google query is discovery only.'],
};
const receipt = { provider: 'deepseek', model: 'fixture-model', requestId: 'test-fixture', generatedAt: '2026-10-26T00:00:00Z', inputTokens: 100, outputTokens: 200 };
const input = { question: draft.question, context: 'Use the official result.', deadline: draft.deadline };

test('rule commitment is order-independent and changes when the actual rule changes', async () => {
  const shuffled = Object.fromEntries(Object.entries(draft).reverse());
  assert.equal(canonicalJson(shuffled), canonicalJson(draft));
  assert.equal(await rulesHash(shuffled), await rulesHash(draft));
  assert.notEqual(await rulesHash({ ...draft, deadline: '2028-01-01T00:00:00Z' }), await rulesHash(draft));
});

test('generation uses authenticated POST and accepts only a valid fixed-question/deadline draft with receipt', async t => {
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    assert.equal(url.href, 'https://rules.example.net/v1/rules');
    assert.equal(init.headers.Authorization, 'Bearer test-access-token');
    assert.equal(init.credentials, 'omit');
    assert.equal(init.redirect, 'error');
    assert.deepEqual(JSON.parse(init.body), input);
    return Response.json({ draft, receipt });
  });
  assert.deepEqual(await generateRules('https://rules.example.net', 'test-access-token', input), { draft, receipt });
});

test('a server error, unsupported provider, missing receipt, changed question or invalid schema cannot masquerade as a generated draft', async t => {
  const samples = [
    new Response('private provider diagnostics', { status: 502 }),
    Response.json({ draft, receipt: { ...receipt, provider: 'mock' } }),
    Response.json({ draft }),
    Response.json({ draft: { ...draft, question: 'A different question' }, receipt }),
    Response.json({ draft: { ...draft, deadline: '2028-01-01T00:00:00Z' }, receipt }),
    Response.json({ draft: { ...draft, allowedSources: [{ name: 'Bad', host: 'javascript:bad', role: 'Official' }] }, receipt }),
  ];
  for (const sample of samples) {
    const mock = t.mock.method(globalThis, 'fetch', async () => sample);
    await assert.rejects(generateRules('https://rules.example.net', 'test-token', input), error => !error.message.includes('private provider diagnostics'));
    mock.mock.restore();
  }
});

test('refuses nonlocal plaintext API connections before sending credentials', async t => {
  const mock = t.mock.method(globalThis, 'fetch', async () => { throw new Error('must not call'); });
  await assert.rejects(generateRules('http://rules.example.net', 'test-token', input), /HTTPS/);
  assert.equal(mock.mock.calls.length, 0);
});

test('saved plans remain local drafts and corrupted or purported deployed plans are rejected', async t => {
  const item = { version: 1, scope: 'local-planning-draft', rules: draft, sha256: await rulesHash(draft), alertsCreated: false, marketDeployed: false };
  let stored = JSON.stringify(item);
  const prior = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => stored } });
  t.after(() => { if (prior) Object.defineProperty(globalThis, 'localStorage', prior); else delete globalThis.localStorage; });
  assert.equal(readSavedDraft().scope, 'local-planning-draft');
  stored = JSON.stringify({ ...item, marketDeployed: true });
  assert.equal(readSavedDraft(), null);
  stored = '{';
  assert.equal(readSavedDraft(), null);
});
