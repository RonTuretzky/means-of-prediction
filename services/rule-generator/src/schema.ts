/** Shared, browser-safe wire schema. No provider, Worker, or secret dependencies. */
export interface RuleRequest {
  question: string;
  context: string;
  deadline: string;
}

export interface RuleDraft {
  question: string;
  eventDefinition: string;
  yesConditions: string[];
  noConditions: string[];
  abstainConditions: string[];
  deadline: string;
  evidenceRequirements: string[];
  allowedSources: Array<{ name: string; host: string; role: string }>;
  alertQueries: Array<{ query: string; job: string }>;
  judgeInstructions: string;
  warnings: string[];
}

export interface RuleReceipt {
  provider: 'deepseek';
  model: string;
  requestId: string;
  generatedAt: string;
  inputTokens: number;
  outputTokens: number;
}

export interface RuleGenerationResponse {
  draft: RuleDraft;
  receipt: RuleReceipt;
}

export type ValidationResult<T> = { ok: true; value: T } | { ok: false; errors: string[] };
export const SOURCE_WARNING = 'Allowed sources are not yet specified or verified; review them before freezing rules.';

const text = (maxLength: number) => ({ type: 'string', minLength: 1, maxLength });
const strings = (minItems: number, maxItems: number, maxLength = 1200) => ({
  type: 'array', minItems, maxItems, items: text(maxLength),
});

export const RULE_REQUEST_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['question', 'context', 'deadline'],
  properties: {
    question: text(500), context: { type: 'string', maxLength: 12000 },
    deadline: { type: 'string', format: 'date-time', maxLength: 40 },
  },
} as const;

export const RULE_DRAFT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['question', 'eventDefinition', 'yesConditions', 'noConditions', 'abstainConditions',
    'deadline', 'evidenceRequirements', 'allowedSources', 'alertQueries', 'judgeInstructions', 'warnings'],
  properties: {
    question: text(500), eventDefinition: text(3000),
    yesConditions: strings(1, 8), noConditions: strings(0, 8), abstainConditions: strings(1, 8),
    deadline: { type: 'string', format: 'date-time', maxLength: 40 },
    evidenceRequirements: strings(1, 12),
    allowedSources: {
      type: 'array', maxItems: 8,
      description: `Use exact public hostnames, never URLs or wildcards. If empty, warnings must include: ${SOURCE_WARNING}`,
      items: {
        type: 'object', additionalProperties: false, required: ['name', 'host', 'role'],
        properties: { name: text(120), host: { ...text(253), format: 'hostname' }, role: text(500) },
      },
    },
    alertQueries: {
      type: 'array', minItems: 1, maxItems: 6,
      items: {
        type: 'object', additionalProperties: false, required: ['query', 'job'],
        properties: { query: text(512), job: text(500) },
      },
    },
    judgeInstructions: text(5000), warnings: strings(1, 12),
  },
} as const;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

const controls = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/;
function validText(value: unknown, maximum: number, allowEmpty = false): value is string {
  return typeof value === 'string' && value.length <= maximum && !controls.test(value)
    && (allowEmpty || value.trim().length > 0);
}

function exactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}

/** Require an explicit timezone and a real Gregorian date, not Date.parse rollover. */
export function validDeadline(value: unknown): value is string {
  if (typeof value !== 'string' || value.length > 40) return false;
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!m) return false;
  const [year, month, day, hour, minute, second] = m.slice(1, 7).map(Number);
  if (year < 1 || month < 1 || month > 12 || day < 1 || hour > 23 || minute > 59 || second > 59) return false;
  const calendar = new Date(0);
  calendar.setUTCFullYear(year, month - 1, day);
  if (calendar.getUTCFullYear() !== year || calendar.getUTCMonth() !== month - 1 || calendar.getUTCDate() !== day) return false;
  if (m[8] !== 'Z' && (Number(m[8].slice(1, 3)) > 23 || Number(m[8].slice(4, 6)) > 59)) return false;
  return Number.isFinite(Date.parse(value));
}

function rawEmail(value: string): boolean {
  return /^(?:DKIM-Signature|Received|Return-Path|Message-ID|MIME-Version|Content-Transfer-Encoding):/im.test(value)
    || (/^From:/im.test(value) && /^To:/im.test(value) && /^Subject:/im.test(value));
}

export function validateRuleRequest(value: unknown): ValidationResult<RuleRequest> {
  if (!isRecord(value) || !exactKeys(value, ['question', 'context', 'deadline'])) {
    return { ok: false, errors: ['Expected only question, context, and deadline.'] };
  }
  const errors: string[] = [];
  if (!validText(value.question, 500)) errors.push('question must contain 1–500 characters.');
  if (!validText(value.context, 12000, true)) errors.push('context must contain at most 12000 characters.');
  if (!validDeadline(value.deadline)) errors.push('deadline must be a valid ISO timestamp with an explicit timezone.');
  if ((typeof value.question === 'string' && rawEmail(value.question))
    || (typeof value.context === 'string' && rawEmail(value.context))) errors.push('Raw email or MIME input is not accepted.');
  if (errors.length) return { ok: false, errors };
  // Preserve the fixed fields byte-for-byte, including the explicit timezone.
  if (typeof value.question === 'string' && typeof value.context === 'string' && typeof value.deadline === 'string') {
    return { ok: true, value: { question: value.question, context: value.context, deadline: value.deadline } };
  }
  return { ok: false, errors: ['Request fields must be strings.'] };
}

function validHost(value: unknown): value is string {
  if (typeof value !== 'string' || value.length > 253 || value !== value.toLowerCase()) return false;
  const labels = value.split('.');
  if (labels.length < 2 || !labels.every(label => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))) return false;
  return /[a-z]/.test(labels.at(-1) ?? '')
    && !/\.(?:invalid|localhost|local|test|example)$/.test(value)
    && !/^(?:example\.com|example\.org|example\.net)$/.test(value);
}

function validStrings(value: unknown, minimum: number, maximum: number): value is string[] {
  return Array.isArray(value) && value.length >= minimum && value.length <= maximum
    && value.every(item => validText(item, 1200));
}

export function validateDraft(value: unknown): value is RuleDraft {
  if (!isRecord(value) || !exactKeys(value, RULE_DRAFT_SCHEMA.required)) return false;
  if (!validText(value.question, 500) || !validText(value.eventDefinition, 3000)
    || !validDeadline(value.deadline) || !validText(value.judgeInstructions, 5000)
    || !validStrings(value.yesConditions, 1, 8) || !validStrings(value.noConditions, 0, 8)
    || !validStrings(value.abstainConditions, 1, 8) || !validStrings(value.evidenceRequirements, 1, 12)
    || !validStrings(value.warnings, 1, 12)) return false;
  if (!Array.isArray(value.allowedSources) || value.allowedSources.length > 8
    || !value.allowedSources.every(source => isRecord(source) && exactKeys(source, ['name', 'host', 'role'])
      && validText(source.name, 120) && validHost(source.host) && validText(source.role, 500))) return false;
  if (value.allowedSources.length === 0 && !value.warnings.includes(SOURCE_WARNING)) return false;
  return Array.isArray(value.alertQueries) && value.alertQueries.length >= 1 && value.alertQueries.length <= 6
    && value.alertQueries.every(query => isRecord(query) && exactKeys(query, ['query', 'job'])
      && validText(query.query, 512) && !/[\r\n]/.test(query.query) && validText(query.job, 500));
}

export function validateRuleDraft(value: unknown): ValidationResult<RuleDraft> {
  return validateDraft(value) ? { ok: true, value } : { ok: false, errors: ['Draft does not satisfy the rule schema.'] };
}
