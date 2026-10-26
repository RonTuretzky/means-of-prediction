import { SYSTEM_PROMPT } from './prompt';
import { isRecord, validateDraft, validateRuleRequest, type RuleGenerationResponse, type RuleRequest } from './schema';
import { PROVIDER_URL, REQUEST_LIMIT, RESPONSE_LIMIT, PROVIDER_TIMEOUT_MS } from './limits';

const encoder = new TextEncoder();

class HttpError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) { super(message); }
}

async function boundedText(body: ReadableStream<Uint8Array> | null, maximum: number): Promise<string> {
  if (!body) throw new HttpError(400, 'invalid_json', 'A JSON body is required.');
  const reader = body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maximum) {
        await reader.cancel();
        throw new HttpError(413, 'body_too_large', 'Body exceeds the allowed size.');
      }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const data = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { data.set(chunk, offset); offset += chunk.byteLength; }
  try { return new TextDecoder('utf-8', { fatal: true, ignoreBOM: false }).decode(data); }
  catch { throw new HttpError(400, 'invalid_json', 'Body must be UTF-8 JSON.'); }
}

function parseJson(text: string): unknown {
  try { return JSON.parse(text); }
  catch { throw new HttpError(400, 'invalid_json', 'Body must be valid JSON.'); }
}

function origins(setting: string): Set<string> {
  const entries = setting.split(',');
  if (!entries.length || entries.some(entry => {
    try {
      const url = new URL(entry);
      return url.origin !== entry || (url.protocol !== 'https:'
        && !(url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname)));
    } catch { return true; }
  })) throw new HttpError(503, 'not_configured', 'Rule generation is not configured.');
  return new Set(entries);
}

function headers(origin: string | null): Headers {
  const result = new Headers({ 'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store', 'Vary': 'Origin', 'X-Content-Type-Options': 'nosniff' });
  if (origin) result.set('Access-Control-Allow-Origin', origin);
  return result;
}

function response(value: unknown, status: number, origin: string | null): Response {
  return new Response(JSON.stringify(value), { status, headers: headers(origin) });
}

async function authenticate(request: Request, secret: string): Promise<string> {
  const auth = request.headers.get('Authorization') ?? '';
  if (!/^Bearer [\x21-\x7e]{1,1024}$/.test(auth)) throw new HttpError(401, 'unauthorized', 'A valid operator token is required.');
  const token = auth.slice(7);
  const [actual, expected] = await Promise.all([
    crypto.subtle.digest('SHA-256', encoder.encode(token)),
    crypto.subtle.digest('SHA-256', encoder.encode(secret)),
  ]);
  if (!crypto.subtle.timingSafeEqual(actual, expected)) throw new HttpError(401, 'unauthorized', 'A valid operator token is required.');
  return Array.from(new Uint8Array(expected), byte => byte.toString(16).padStart(2, '0')).join('');
}

function tokenCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}

async function generate(input: RuleRequest, env: Env): Promise<RuleGenerationResponse> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), PROVIDER_TIMEOUT_MS);
  try {
    const provider = await fetch(PROVIDER_URL, {
      method: 'POST', redirect: 'manual', signal: controller.signal,
      headers: { 'Authorization': `Bearer ${env.DEEPSEEK_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: env.DEEPSEEK_MODEL, max_tokens: 2500, stream: false,
        thinking: { type: 'disabled' }, response_format: { type: 'json_object' },
        messages: [
          { role: 'system', content: SYSTEM_PROMPT },
          { role: 'user', content: JSON.stringify({ ...input, currentTime: new Date().toISOString() }) },
        ],
      }),
    });
    if (!provider.ok) {
      await provider.body?.cancel();
      throw new Error('provider_error');
    }
    const contentType = provider.headers.get('Content-Type')?.split(';')[0].trim();
    if (contentType !== 'application/json') { await provider.body?.cancel(); throw new Error('provider_format'); }
    const result = parseJson(await boundedText(provider.body, RESPONSE_LIMIT));
    if (!isRecord(result) || typeof result.id !== 'string' || !/^[a-zA-Z0-9_-]{1,200}$/.test(result.id)
      || typeof result.model !== 'string' || !/^[a-zA-Z0-9_.:-]{1,150}$/.test(result.model)
      || !Array.isArray(result.choices) || result.choices.length !== 1
      || !isRecord(result.usage) || !tokenCount(result.usage.prompt_tokens) || !tokenCount(result.usage.completion_tokens)) {
      throw new Error('provider_shape');
    }
    const choice = result.choices[0];
    if (!isRecord(choice) || choice.finish_reason !== 'stop' || !isRecord(choice.message)
      || choice.message.role !== 'assistant' || typeof choice.message.content !== 'string'
      || choice.message.tool_calls != null || choice.message.function_call != null
      || choice.message.refusal != null) throw new Error('provider_incomplete');
    const draft = parseJson(choice.message.content);
    if (!validateDraft(draft) || draft.question !== input.question || draft.deadline !== input.deadline) {
      throw new Error('provider_invalid_draft');
    }
    const answer: RuleGenerationResponse = {
      draft,
      receipt: { provider: 'deepseek', model: result.model, requestId: result.id,
        generatedAt: new Date().toISOString(), inputTokens: result.usage.prompt_tokens, outputTokens: result.usage.completion_tokens },
    };
    if (encoder.encode(JSON.stringify(answer)).byteLength > RESPONSE_LIMIT) throw new Error('provider_oversize');
    return answer;
  } catch {
    // Never expose/log upstream bodies, headers, prompt text, or exception details.
    if (controller.signal.aborted) throw new HttpError(504, 'provider_timeout', 'Rule generation timed out.');
    throw new HttpError(502, 'provider_failure', 'The provider did not return a complete valid rule draft.');
  } finally { clearTimeout(timeout); }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    let allowedOrigin: string | null = null;
    try {
      const url = new URL(request.url);
      if (url.pathname !== '/v1/rules' || url.search) throw new HttpError(404, 'not_found', 'Not found.');
      if (!env.ALLOWED_ORIGINS) throw new HttpError(503, 'not_configured', 'Rule generation is not configured.');
      const allowlist = origins(env.ALLOWED_ORIGINS);
      const origin = request.headers.get('Origin');
      if (origin && !allowlist.has(origin)) throw new HttpError(403, 'origin_denied', 'Origin is not allowed.');
      allowedOrigin = origin;
      if (request.method === 'OPTIONS') {
        const requestedHeaders = (request.headers.get('Access-Control-Request-Headers') ?? '')
          .split(',').map(value => value.trim().toLowerCase()).filter(Boolean);
        if (!origin || request.headers.get('Access-Control-Request-Method') !== 'POST'
          || requestedHeaders.some(name => !['authorization', 'content-type'].includes(name))) {
          throw new HttpError(403, 'preflight_denied', 'Preflight is not allowed.');
        }
        const cors = headers(origin);
        cors.set('Access-Control-Allow-Methods', 'POST');
        cors.set('Access-Control-Allow-Headers', 'Authorization, Content-Type');
        cors.set('Access-Control-Max-Age', '600');
        return new Response(null, { status: 204, headers: cors });
      }
      if (request.method !== 'POST') throw new HttpError(405, 'method_not_allowed', 'Use POST.');
      if (!env.RULE_GENERATOR_TOKEN || env.RULE_GENERATOR_TOKEN.length < 32 || !env.DEEPSEEK_API_KEY
        || !env.DEEPSEEK_MODEL || !/^deepseek-[a-zA-Z0-9_.-]{1,100}$/.test(env.DEEPSEEK_MODEL)
        || !env.RULES_RATE_LIMITER || typeof env.RULES_RATE_LIMITER.limit !== 'function') {
        throw new HttpError(503, 'not_configured', 'Rule generation is not configured.');
      }
      const tokenKey = await authenticate(request, env.RULE_GENERATOR_TOKEN);
      let permitted: boolean;
      try { permitted = (await env.RULES_RATE_LIMITER.limit({ key: `rules:${tokenKey}` })).success; }
      catch { throw new HttpError(503, 'rate_limit_unavailable', 'Rule generation is temporarily unavailable.'); }
      if (!permitted) throw new HttpError(429, 'rate_limited', 'Too many rule-generation requests. Try again later.');
      if (request.headers.get('Content-Type')?.split(';')[0].trim() !== 'application/json'
        || (request.headers.has('Content-Encoding') && request.headers.get('Content-Encoding') !== 'identity')) {
        throw new HttpError(415, 'unsupported_media_type', 'Send uncompressed application/json.');
      }
      const length = request.headers.get('Content-Length');
      if (length && (!/^\d+$/.test(length) || Number(length) > REQUEST_LIMIT)) {
        throw new HttpError(413, 'body_too_large', 'Body exceeds 24 KiB.');
      }
      const input = validateRuleRequest(parseJson(await boundedText(request.body, REQUEST_LIMIT)));
      if (!input.ok) return response({ error: { code: 'invalid_request', message: input.errors.join(' ') } }, 400, allowedOrigin);
      return response(await generate(input.value, env), 200, allowedOrigin);
    } catch (error) {
      const failure = error instanceof HttpError ? error : new HttpError(500, 'internal_error', 'Rule generation failed.');
      const result = response({ error: { code: failure.code, message: failure.message } }, failure.status, allowedOrigin);
      if (failure.status === 429) result.headers.set('Retry-After', '60');
      if (failure.status === 401) result.headers.set('WWW-Authenticate', 'Bearer');
      return result;
    }
  },
} satisfies ExportedHandler<Env>;
