import { type MarketData, ContentField } from "../hooks/useMarkets";
import { parseCategory, stripCategoryTag } from "../data/categories";
import { BODY_PARSING } from "../config";
import { fmtDate } from "../lib/format";

/** Mirrors JudgePrompt.MAX_CRITERIA_BYTES (contracts/src/judge/JudgePrompt.sol). */
export const MAX_CRITERIA_BYTES = 1200;

/** The judge the fleet runs for us (docs/GASKILLER-LLM-SETTLEMENT.md). */
export const JUDGE_MODEL = "Qwen3.5-35B";

export const JUDGE_TRUST_LINE =
  "Judged by Qwen3.5-35B running on Gas Killer's operator set - attested, not proven; can only move on a real DKIM-signed alert from a listed newspaper.";

/**
 * Normalise creator-typed resolution rules into the one-line form the contract accepts
 * (JudgePrompt.isSafeMarketText): newlines collapse to spaces, '<' is rejected (the
 * chat-template control strings all start with it), and the UTF-8 length is capped.
 */
export function sanitizeCriteria(raw: string): { valid: boolean; value: string; error: string | null } {
  const value = raw.replace(/[\r\n]+/g, " ").replace(/ {2,}/g, " ").trim();
  if (!value) return { valid: false, value, error: "Enter the resolution rules" };
  if (value.includes("<")) return { valid: false, value, error: "'<' is not allowed" };
  const bytes = new TextEncoder().encode(value).length;
  if (bytes > MAX_CRITERIA_BYTES) return { valid: false, value, error: `${bytes} bytes (max ${MAX_CRITERIA_BYTES})` };
  return { valid: true, value, error: null };
}

/** Small "AI-judged" chip, same shape as the category tabs. */
export function ResolutionBadge({ className = "" }: { className?: string }) {
  return (
    <span
      data-testid="judged-chip"
      title={JUDGE_TRUST_LINE}
      className={`inline-block border-2 border-core-orange bg-[#FBDED1] px-2 py-0.5 text-caption font-bold uppercase text-core-orange ${className}`}
    >
      AI-judged
    </span>
  );
}

const FIELD_LABEL: Record<ContentField, string> = {
  [ContentField.Subject]: "Subject line",
  [ContentField.Body]: "Body",
  [ContentField.SubjectOrBody]: "Subject or body",
};

/** Polymarket's "Rules" section: verbatim resolution criteria + resolver transparency. */
export function RulesPanel({ m }: { m: MarketData }) {
  const category = parseCategory(m.description);
  return (
    <div data-testid="rules-panel">
      <p className="mb-3 whitespace-pre-wrap text-sm">{stripCategoryTag(m.description)}</p>

      <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
        {category && (
          <>
            <span className="text-surface-grey-2">Category</span>
            <span className="font-bold">{category}</span>
          </>
        )}
        {m.judged ? (
          <>
            <span className="text-surface-grey-2">Resolution rules (AI-judged)</span>
            <span data-testid="rules-criteria">
              <ResolutionBadge className="mb-1" />
              <p className="whitespace-pre-wrap border-2 border-surface-ink bg-paper-1 px-2 py-1.5">{m.criteria}</p>
              <p className="mt-1 text-caption text-surface-grey-2">{JUDGE_TRUST_LINE}</p>
            </span>
            <span className="text-surface-grey-2">Judge</span>
            <span className="font-mono text-caption" data-testid="rules-judge">
              {m.judge} (LLMJudge contract — verdicts keyed by the exact prompt over the signed subject line)
            </span>
          </>
        ) : (
          <>
            <span className="text-surface-grey-2">Condition</span>
            <span>
              <code className="bg-paper-1 px-1 py-0.5 font-mono text-caption">{m.contentRegex || "(per-source)"}</code>{" "}
              on the {FIELD_LABEL[m.contentField].toLowerCase()}
            </span>
          </>
        )}
        {BODY_PARSING && m.contentField !== ContentField.Subject && !m.judged && (
          <>
            <span className="text-surface-grey-2">Body evidence</span>
            <span className="text-caption">A substring of authenticated single-part plain text or HTML source. HTML tags and entities remain text. Quoted-printable is decoded; an unsigned encoding header cannot change that rule. Multipart is unsupported. The full body becomes public, with multiple paid uploads for large emails.</span>
          </>
        )}
        <span className="text-surface-grey-2">Threshold</span>
        <span>
          {m.threshold} of {m.sources.length} newspapers
        </span>
        <span className="text-surface-grey-2">Sources</span>
        <span>
          {m.sources.map((s, i) => (
            <span key={i} className="mr-2 inline-block">
              <b>{s.name}</b>{" "}
              <code className="bg-paper-1 px-1 font-mono text-caption">
                d={s.dkimDomain}
                {s.fromRegex ? ` from~/${s.fromRegex}/` : ""}
              </code>
              {s.contentRegex && (
                <code className="ml-1 bg-paper-1 px-1 font-mono text-caption">content~/{s.contentRegex}/</code>
              )}
            </span>
          ))}
        </span>
        <span className="text-surface-grey-2">Email window</span>
        <span>
          {fmtDate(m.windowStart)} → {fmtDate(m.deadline)}
        </span>
        <span className="text-surface-grey-2">NO buffer</span>
        <span>{Number(m.resolutionBuffer) / 3600} hours after deadline</span>
        <span className="text-surface-grey-2">Resolver</span>
        <span className="font-mono text-caption">
          {m.market} (this market contract — DKIM proofs only{m.judged ? ", verdicts read from the judge" : ""})
        </span>
        <span className="text-surface-grey-2">Collateral</span>
        <span>
          {m.collateral.symbol} <span className="font-mono text-caption">({m.collateral.address})</span>
        </span>
        <span className="text-surface-grey-2">Creator</span>
        <span className="font-mono text-caption">{m.creator}</span>
        <span className="text-surface-grey-2">Opened</span>
        <span>{fmtDate(m.createdAt)}</span>
      </div>
    </div>
  );
}
