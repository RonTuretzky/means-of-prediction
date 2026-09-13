import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Button, Chip, Heading1 } from "@breadcoop/ui";
import { CheckCircle, Plus, Trash, WarningCircle } from "@phosphor-icons/react";
import { maxUint256, zeroAddress } from "viem";
import { abis } from "../contracts/gen";
import { NEWSPAPERS } from "../data/newspapers";
import { tokensForChain, type TokenInfo } from "../data/tokens";
import { CHAIN_ID } from "../config";
import { KeywordBuilder, phrasesToRegex, regexToPhrases } from "../components/KeywordBuilder";
import { AIRegexPanel } from "../components/AIRegexPanel";
import { CATEGORIES, withCategoryTag, type Category } from "../data/categories";
import { substringPattern } from "../lib/body";
import { BODY_PARSING } from "../config";
import { ContentField, FACTORY, USDC, useCash } from "../hooks/useMarkets";
import { ResolutionBadge, sanitizeCriteria, MAX_CRITERIA_BYTES } from "../components/RulesPanel";
import { parseAmount } from "../lib/format";
import { publicClient, useWallet } from "../lib/wallet";
import { explain } from "../components/TradeWidget";

interface SourceDraft {
  name: string;
  dkimDomain: string;
  fromRegex: string;
  contentRegex: string;
}

const STEPS = ["Question", "Newspapers", "Condition", "Market"] as const;

type ConditionMode = "simple" | "advanced" | "ai" | "judged";

/** The factory's LLMJudge oracle; address(0) = this network cannot host AI-judged markets. */
function useFactoryJudge() {
  return useQuery({
    queryKey: ["factory-judge", FACTORY],
    staleTime: Infinity,
    queryFn: async () => {
      try {
        return (await publicClient.readContract({
          address: FACTORY,
          abi: abis.MarketFactory,
          functionName: "judge",
        })) as `0x${string}`;
      } catch {
        return zeroAddress; // older factory without judge()
      }
    },
  });
}

export function CreatePage() {
  const wallet = useWallet();
  const navigate = useNavigate();
  const { data: cash } = useCash(wallet.address);
  const { data: platformFee = 0n } = useQuery({
    queryKey: ["factory-protocol-fee", FACTORY],
    queryFn: async () => {
      try { return await publicClient.readContract({ address: FACTORY, abi: abis.MarketFactory, functionName: "protocolFee" }) as bigint; }
      catch { return 0n; } // legacy factories have no platform fee
    },
  });
  const platformPct = Number(platformFee) / 1e16;

  const [step, setStep] = useState(0);
  const [question, setQuestion] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<Category | null>(null);
  const [sources, setSources] = useState<SourceDraft[]>([
    { ...NEWSPAPERS[0], contentRegex: "" },
    { ...NEWSPAPERS[1], contentRegex: "" },
  ]);
  const [threshold, setThreshold] = useState(2);
  const [regexMode, setRegexMode] = useState<ConditionMode>("simple");
  const [criteriaRaw, setCriteriaRaw] = useState("");
  const { data: factoryJudge } = useFactoryJudge();
  const judgeAvailable = !!factoryJudge && factoryJudge !== zeroAddress;
  const judged = regexMode === "judged";
  const [phrases, setPhrases] = useState<string[]>([]);
  const [contentRegex, setContentRegex] = useState("");
  // Subject is the default; fresh deployments also accept authenticated body-source windows.
  const [contentField, setContentField] = useState<ContentField>(ContentField.Subject);
  const collateralOptions = tokensForChain(CHAIN_ID, USDC);
  const [collateral, setCollateral] = useState<TokenInfo>(collateralOptions[0]);
  const bodyPatternValid = contentField !== ContentField.Body || substringPattern(contentRegex);
  const [testSubject, setTestSubject] = useState("Breaking News: ");
  const [days, setDays] = useState(30);
  const [bufferHours, setBufferHours] = useState(24);
  const [liquidity, setLiquidity] = useState("1000");
  const [feePct, setFeePct] = useState("2");
  const [startYes, setStartYes] = useState(50); // starting YES price in cents
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setPhrasesAndRegex = (next: string[]) => {
    setPhrases(next);
    setContentRegex(phrasesToRegex(next));
  };
  const switchMode = (mode: ConditionMode) => {
    if (mode === "judged" && !judgeAvailable) return;
    if (mode === "simple") {
      // best-effort: recover phrases from a simple alternation pattern
      const recovered = regexToPhrases(contentRegex);
      setPhrases(recovered);
      if (recovered.length) setContentRegex(phrasesToRegex(recovered));
    }
    setRegexMode(mode);
  };

  // Live regex feedback using the browser's own RegExp — the same subset the
  // onchain engine implements (differentially tested against JS in Foundry).
  const regexState = useMemo(() => {
    if (!contentRegex) return { valid: false, matches: false, error: "Enter a pattern" };
    try {
      let src = contentRegex;
      let flags = "";
      if (src.startsWith("(?i)")) {
        src = src.slice(4);
        flags = "i";
      }
      const re = new RegExp(src, flags);
      return { valid: true, matches: re.test(testSubject), error: null as string | null };
    } catch (e) {
      return { valid: false, matches: false, error: (e as Error).message };
    }
  }, [contentRegex, testSubject]);

  // Judged mode: one-line criteria, no '<' (prompt-injection guard), <= 1200 bytes — the
  // same rules HeadlineMarket.initialize enforces via JudgePrompt.isSafeMarketText.
  const criteriaState = useMemo(() => {
    if (!judged) return { valid: true, value: "", error: null as string | null };
    return sanitizeCriteria(criteriaRaw);
  }, [judged, criteriaRaw]);
  const criteria = criteriaState.value;
  const conditionValid = judged ? criteriaState.valid : regexState.valid && bodyPatternValid;

  const toggleNewspaper = (i: number) => {
    const preset = NEWSPAPERS[i];
    setSources((cur) => {
      const found = cur.findIndex((s) => s.dkimDomain === preset.dkimDomain);
      if (found >= 0) {
        const next = cur.filter((_, j) => j !== found);
        setThreshold((t) => Math.max(1, Math.min(t, next.length || 1)));
        return next;
      }
      return [...cur, { ...preset, contentRegex: "" }];
    });
  };

  const canContinue = [
    question.trim().length > 3,
    sources.length > 0 && threshold >= 1 && threshold <= sources.length,
    conditionValid,
    true,
  ][step];

  const create = async () => {
    if (!bodyPatternValid) { setError("Body rules cannot use ^ or $ anchors"); return; }
    setBusy(true);
    setError(null);
    try {
      const liq = parseAmount(liquidity, collateral.decimals) ?? 0n;
      if (liq > 0n) {
        const allowance = (await publicClient.readContract({
          address: collateral.address,
          abi: abis.TestUSDC, // standard ERC-20 subset
          functionName: "allowance",
          args: [wallet.address, FACTORY],
        })) as bigint;
        if (allowance < liq) {
          await wallet.write({
            address: collateral.address,
            abi: abis.TestUSDC,
            functionName: "approve",
            args: [FACTORY, maxUint256],
          });
        }
      }

      const now = Number((await publicClient.getBlock()).timestamp);
      // distributionHint sets the opening odds: pool keeps more of the cheap side.
      // YES price = noBal / (yesBal + noBal), so hint = [100 - startYes, startYes].
      const hint =
        startYes === 50 ? [] : [BigInt(100 - startYes), BigInt(startYes)];

      const conditionText = judged
        ? ` breaking-news alert email whose subject line an on-chain language model judges to satisfy the resolution rules,`
        : ` breaking-news alert email matching /${contentRegex}/ on the` +
          ` ${contentField === ContentField.Subject ? "subject" : contentField === ContentField.Body ? "body" : "subject or body"},`;
      // Struct field order follows the forge artifact (CreateMarketParams): regex, then criteria.
      const params = {
        question: question.trim(),
        description: withCategoryTag(
          description.trim() ||
            `Resolves YES if at least ${threshold} of ${sources.length} configured newspapers send a` +
              conditionText +
              ` dated before the deadline. Settled permissionlessly by a real DKIM signature verified onchain;` +
              ` resolves NO` +
              ` ${bufferHours}h after the deadline if the threshold is not met.`,
          category,
        ),
        contentRegex: judged ? "" : contentRegex,
        criteria: judged ? criteria : "",
        contentField: judged ? ContentField.Subject : contentField,
        sources: sources.map((s) => ({
          name: s.name,
          dkimDomain: s.dkimDomain,
          fromRegex: s.fromRegex,
          // judged markets take no per-source regex overrides
          contentRegex: judged ? "" : s.contentRegex,
        })),
        threshold,
        windowStart: BigInt(now),
        deadline: BigInt(now + days * 86400),
        resolutionBuffer: BigInt(bufferHours * 3600),
        collateralToken: collateral.address,
        fee: BigInt(Math.round(parseFloat(feePct || "0") * 1e16)),
        initialLiquidity: liq,
        distributionHint: hint,
      };

      await wallet.write({
        address: FACTORY,
        abi: abis.MarketFactory,
        functionName: "createMarket",
        args: [params],
      });

      const count = (await publicClient.readContract({
        address: FACTORY,
        abi: abis.MarketFactory,
        functionName: "marketCount",
      })) as bigint;
      navigate(`/market/${Number(count) - 1}`);
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <Heading1>Create a market</Heading1>
      <p className="mb-6 text-body text-surface-grey-2">
        Permissionless: no approval, no whitelist. You choose the newspapers, the condition (regex or AI-judged rules)
        and the token.
      </p>

      <ol className="mb-6 flex flex-wrap gap-2">
        {STEPS.map((s, i) => (
          <li key={s}>
            <button
              onClick={() => i < step && setStep(i)}
              className={`border-2 border-surface-ink px-3 py-1 text-sm font-bold uppercase ${
                i === step ? "bg-core-orange text-white" : i < step ? "bg-paper-0" : "bg-paper-2 text-surface-grey"
              }`}
            >
              {i + 1}. {s}
            </button>
          </li>
        ))}
      </ol>

      <div className="bread-card p-5">
        {step === 0 && (
          <div className="space-y-4">
            <div>
              <label className="text-caption font-bold uppercase text-surface-grey-2">Question</label>
              <input
                data-testid="create-question"
                placeholder="Will the Fed cut rates before October 2026?"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                className="w-full border-2 border-surface-ink bg-paper-0 px-3 py-2 text-lg outline-none focus:border-core-orange"
              />
              <p className="mt-1 text-caption text-surface-grey-2">
                Phrase it so a breaking-news headline can answer it unambiguously.
              </p>
            </div>
            <div>
              <label className="text-caption font-bold uppercase text-surface-grey-2">
                Resolution rules (optional — generated if blank)
              </label>
              <textarea
                data-testid="create-description"
                rows={4}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full border-2 border-surface-ink bg-paper-0 px-3 py-2 outline-none focus:border-core-orange"
              />
            </div>
            <div>
              <label className="text-caption font-bold uppercase text-surface-grey-2">Category (optional)</label>
              <div className="mt-1 flex flex-wrap gap-1.5" data-testid="create-category">
                {CATEGORIES.map((c) => (
                  <button
                    key={c}
                    data-testid={`category-${c}`}
                    onClick={() => setCategory((cur) => (cur === c ? null : c))}
                    className={`border-2 px-2.5 py-1 text-sm font-bold ${
                      category === c ? "border-core-orange bg-[#FBDED1]" : "border-surface-ink bg-paper-0"
                    }`}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <div>
              <label className="text-caption font-bold uppercase text-surface-grey-2">
                Newspapers ({sources.length} selected)
              </label>
              <div className="mt-2 grid gap-2 sm:grid-cols-2" data-testid="newspaper-picker">
                {NEWSPAPERS.map((n, i) => {
                  const on = sources.some((s) => s.dkimDomain === n.dkimDomain);
                  return (
                    <button
                      key={n.dkimDomain}
                      data-testid={`newspaper-${n.dkimDomain}`}
                      onClick={() => toggleNewspaper(i)}
                      className={`border-2 p-2 text-left ${
                        on ? "border-core-orange bg-[#FBDED1]" : "border-surface-ink bg-paper-0"
                      }`}
                    >
                      <div className="flex items-center gap-1 font-bold">
                        {on && <CheckCircle size={16} weight="fill" className="text-core-orange" />}
                        {n.name}
                        {n.verified && <Chip size="small">verified sender</Chip>}
                      </div>
                      <div className="font-mono text-caption text-surface-grey-2">d={n.dkimDomain}</div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <label className="text-caption font-bold uppercase text-surface-grey-2">Custom source</label>
              <CustomSourceForm onAdd={(s) => setSources((cur) => [...cur, s])} />
            </div>

            {sources.length > 0 && (
              <div>
                <label className="text-caption font-bold uppercase text-surface-grey-2">Selected sources</label>
                <ul className="mt-1 space-y-1" data-testid="selected-sources">
                  {sources.map((s, i) => (
                    <li key={i} className="flex items-center gap-2 border-2 border-surface-ink bg-paper-0 px-2 py-1">
                      <span className="font-bold">{s.name}</span>
                      <code className="font-mono text-caption text-surface-grey-2">
                        d={s.dkimDomain} from~/{s.fromRegex || ".*"}/
                      </code>
                      <button
                        className="ml-auto text-system-red"
                        onClick={() => setSources((cur) => cur.filter((_, j) => j !== i))}
                        aria-label={`Remove ${s.name}`}
                      >
                        <Trash size={16} />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <label className="text-caption font-bold uppercase text-surface-grey-2">
                Threshold: {threshold} of {sources.length} must report
              </label>
              <input
                data-testid="create-threshold"
                type="range"
                min={1}
                max={Math.max(1, sources.length)}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
                className="w-full accent-[#EA5817]"
              />
              <p className="text-caption text-surface-grey-2">
                Requiring 2+ independent newspapers makes a single compromised sender insufficient to settle.
              </p>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <div className="flex border-2 border-surface-ink">
              <button
                data-testid="mode-simple"
                onClick={() => switchMode("simple")}
                className={`flex-1 px-3 py-2 font-breadDisplay font-bold uppercase ${
                  regexMode === "simple" ? "bg-surface-ink text-paper-0" : "bg-paper-0"
                }`}
              >
                Plain words
              </button>
              <button
                data-testid="mode-advanced"
                onClick={() => switchMode("advanced")}
                className={`flex-1 px-3 py-2 font-breadDisplay font-bold uppercase ${
                  regexMode === "advanced" ? "bg-surface-ink text-paper-0" : "bg-paper-0"
                }`}
              >
                Advanced (regex)
              </button>
              <button
                data-testid="mode-ai"
                onClick={() => switchMode("ai")}
                className={`flex-1 px-3 py-2 font-breadDisplay font-bold uppercase ${
                  regexMode === "ai" ? "bg-surface-ink text-paper-0" : "bg-paper-0"
                }`}
              >
                AI (describe it)
              </button>
              <button
                data-testid="mode-judged"
                onClick={() => switchMode("judged")}
                disabled={!judgeAvailable}
                title={
                  judgeAvailable
                    ? "Settle by an on-chain language model judging the subject line against plain-English rules"
                    : "AI-judged markets are unavailable on this network: the factory has no LLMJudge (judge() is the zero address)"
                }
                className={`flex-1 px-3 py-2 font-breadDisplay font-bold uppercase ${
                  regexMode === "judged" ? "bg-surface-ink text-paper-0" : "bg-paper-0"
                } disabled:cursor-not-allowed disabled:text-surface-grey`}
              >
                AI-judged
              </button>
            </div>

            {regexMode === "judged" ? (
              <div>
                <label className="text-caption font-bold uppercase text-surface-grey-2">
                  Resolution rules (judged against the subject line)
                </label>
                <textarea
                  data-testid="create-criteria"
                  rows={6}
                  placeholder="Resolves YES if the Federal Reserve announces a cut to its benchmark interest rate. Forecasts, expectations or calls for a cut do not count; only an announced decision."
                  value={criteriaRaw}
                  onChange={(e) => setCriteriaRaw(e.target.value)}
                  className="w-full border-2 border-surface-ink bg-paper-0 px-3 py-2 outline-none focus:border-core-orange"
                />
                <div className="mt-1 flex items-start justify-between gap-2 text-caption">
                  <span className="text-surface-grey-2">
                    Newlines are collapsed to spaces; <code>&lt;</code> is not allowed.{" "}
                    {new TextEncoder().encode(criteria).length}/{MAX_CRITERIA_BYTES} bytes.
                  </span>
                  {criteriaState.error && (
                    <span className="flex shrink-0 items-center gap-1 font-bold text-system-red" data-testid="criteria-error">
                      <WarningCircle size={14} /> {criteriaState.error}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-caption text-surface-grey-2">
                  Settled by an on-chain language model (Qwen3.5-35B via Gas Killer) judging the DKIM-signed subject
                  line against these rules. Attested by the Gas Killer operator set, not proven on-chain.
                </p>
                <div className="mt-2">
                  <ResolutionBadge />
                </div>
              </div>
            ) : regexMode === "simple" ? (
              <>
                <KeywordBuilder phrases={phrases} onChange={setPhrasesAndRegex} />
                {contentRegex && (
                  <p className="text-caption text-surface-grey-2">
                    Generated condition:{" "}
                    <code className="bg-paper-1 px-1 py-0.5 font-mono">{contentRegex}</code>
                  </p>
                )}
              </>
            ) : regexMode === "ai" ? (
              <AIRegexPanel currentRegex={contentRegex} onGenerated={setContentRegex} />
            ) : (
              <div>
                <label className="text-caption font-bold uppercase text-surface-grey-2">Content regex</label>
                <input
                  data-testid="create-regex"
                  placeholder="(?i)fed (cuts|lowers|slashes) (interest )?rates"
                  value={contentRegex}
                  onChange={(e) => setContentRegex(e.target.value)}
                  className="w-full border-2 border-surface-ink bg-paper-0 px-3 py-2 font-mono outline-none focus:border-core-orange"
                />
                <p className="mt-1 text-caption text-surface-grey-2">
                  Evaluated onchain by RegexLib. Supports literals, <code>. * + ? {"{m,n}"}</code>, classes,
                  groups, alternation, anchors, <code>\d \w \s</code> and a <code>(?i)</code> case-insensitive
                  prefix. Not supported: lookaround, backreferences.
                </p>
              </div>
            )}

            {!judged && (
              <>
            <div>
              <label className="text-caption font-bold uppercase text-surface-grey-2">Match against</label>
              {!bodyPatternValid && <p role="alert" className="text-red-700">Body patterns cannot use ^ or $ anchors.</p>}
              <div className="flex gap-2">
                {[
                  [ContentField.Subject, "Subject"],
                  [ContentField.Body, "Body"],
                  [ContentField.SubjectOrBody, "Subject or body"],
                ].map(([v, label]) => (
                  <button
                    key={label as string}
                    data-testid={`field-${label}`}
                    disabled={v !== ContentField.Subject && !BODY_PARSING}
                    title={v !== ContentField.Subject && !BODY_PARSING ? "This deployment needs the body verifier upgrade." : undefined}
                    onClick={() => setContentField(v as ContentField)}
                    className={`border-2 border-surface-ink px-3 py-1.5 text-sm font-bold ${
                      contentField === v ? "bg-surface-ink text-paper-0" : "bg-paper-0"
                    } disabled:cursor-not-allowed disabled:border-surface-grey disabled:bg-paper-2 disabled:text-surface-grey`}
                  >
                    {label as string}
                  </button>
                ))}
              </div>
              <p className="mt-1 text-caption text-surface-grey-2">
                {BODY_PARSING ? "Body rules match a decoded excerpt authenticated against the complete signed body hash. HTML markup is retained. Use substring patterns without ^ or $ anchors; multipart and base64 messages are not supported in this version." : "Body proofs require a fresh deployment with the upgraded verifier."}

              </p>
            </div>

            <div>
              <label className="text-caption font-bold uppercase text-surface-grey-2">
                Test against a sample headline
              </label>
              <input
                data-testid="create-test-subject"
                value={testSubject}
                onChange={(e) => setTestSubject(e.target.value)}
                className="w-full border-2 border-surface-ink bg-paper-0 px-3 py-2 outline-none"
              />
              <div className="mt-2" data-testid="regex-feedback">
                {!regexState.valid ? (
                  <span className="flex items-center gap-1 font-bold text-system-red">
                    <WarningCircle size={16} /> {regexState.error}
                  </span>
                ) : regexState.matches ? (
                  <span className="flex items-center gap-1 font-bold text-system-green">
                    <CheckCircle size={16} weight="fill" /> Matches — this headline would settle YES
                  </span>
                ) : (
                  <span className="font-bold text-surface-grey-2">Valid pattern, but this headline doesn't match</span>
                )}
              </div>
            </div>
              </>
            )}
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="text-caption font-bold uppercase text-surface-grey-2">Deadline (days)</label>
                <input
                  data-testid="create-days"
                  type="number"
                  min={1}
                  value={days}
                  onChange={(e) => setDays(Number(e.target.value))}
                  className="w-full border-2 border-surface-ink bg-paper-0 px-3 py-2 outline-none"
                />
              </div>
              <div>
                <label className="text-caption font-bold uppercase text-surface-grey-2">NO buffer (hours)</label>
                <input
                  data-testid="create-buffer"
                  type="number"
                  min={0}
                  value={bufferHours}
                  onChange={(e) => setBufferHours(Number(e.target.value))}
                  className="w-full border-2 border-surface-ink bg-paper-0 px-3 py-2 outline-none"
                />
              </div>
              <div>
                <label className="text-caption font-bold uppercase text-surface-grey-2">Collateral token</label>
                <select
                  data-testid="create-collateral"
                  className="w-full border-2 border-surface-ink bg-paper-0 px-3 py-2 font-bold outline-none"
                  value={collateral.address}
                  onChange={(e) =>
                    setCollateral(collateralOptions.find((t) => t.address === e.target.value) ?? collateralOptions[0])
                  }
                >
                  {collateralOptions.map((t) => (
                    <option key={t.address} value={t.address}>
                      {t.symbol}
                    </option>
                  ))}
                </select>
                <p className="text-caption text-surface-grey-2">{collateral.note}</p>
              </div>
              <div>
                <label className="text-caption font-bold uppercase text-surface-grey-2">
                  Initial liquidity ({collateral.symbol})
                </label>
                <input
                  data-testid="create-liquidity"
                  value={liquidity}
                  onChange={(e) => setLiquidity(e.target.value)}
                  className="w-full border-2 border-surface-ink bg-paper-0 px-3 py-2 outline-none"
                />
                {collateral.faucet && (
                  <p className="text-caption text-surface-grey-2">
                    Your cash: {cash !== undefined ? (Number(cash) / 1e6).toFixed(2) : "…"} USDC
                  </p>
                )}
              </div>
              <div>
                <label className="text-caption font-bold uppercase text-surface-grey-2">Liquidity-provider fee (%)</label>
                <input
                  data-testid="create-fee"
                  value={feePct}
                  onChange={(e) => setFeePct(e.target.value)}
                  className="w-full border-2 border-surface-ink bg-paper-0 px-3 py-2 outline-none"
                />
                <p className="text-caption text-surface-grey-2">Paid to liquidity providers on every trade. The platform adds {platformPct}%, for {Number(feePct || 0) + platformPct}% total.</p>
              </div>
            </div>

            <div>
              <label className="text-caption font-bold uppercase text-surface-grey-2">
                Opening odds: YES at {startYes}¢ / NO at {100 - startYes}¢
              </label>
              <input
                data-testid="create-odds"
                type="range"
                min={5}
                max={95}
                step={5}
                value={startYes}
                onChange={(e) => setStartYes(Number(e.target.value))}
                className="w-full accent-[#EA5817]"
              />
            </div>

            <div className="border-2 border-surface-ink bg-paper-1 p-3 text-sm">
              <div className="mb-1 font-bold uppercase">Summary</div>
              <p>
                <b>{question || "(no question)"}</b>
              </p>
              <p className="text-surface-grey-2">
                {threshold} of {sources.length} newspapers ·{" "}
                {judged ? (
                  <>AI-judged: “{criteria.length > 80 ? `${criteria.slice(0, 80)}…` : criteria}” · subject</>
                ) : (
                  <>
                    /{contentRegex}/ ·{" "}
                    {contentField === ContentField.Subject
                      ? "subject"
                      : contentField === ContentField.Body
                        ? "body"
                        : "subject or body"}
                  </>
                )}{" "}
                · {days}d deadline · {feePct}% LP + {platformPct}% platform fee · {liquidity} {collateral.symbol} seed
              </p>
            </div>

            {error && (
              <div className="border-2 border-system-red bg-red-0 px-2 py-1 text-sm text-system-red">{error}</div>
            )}
          </div>
        )}

        <div className="mt-6 flex justify-between">
          <Button variant="light" disabled={step === 0 || busy} onClick={() => setStep((s) => s - 1)}>
            Back
          </Button>
          {step < STEPS.length - 1 ? (
            <Button data-testid="create-next" disabled={!canContinue} onClick={() => setStep((s) => s + 1)}>
              Continue
            </Button>
          ) : !wallet.connected ? (
            <Button data-testid="create-connect" onClick={() => wallet.connect().catch((e) => setError(explain(e)))}>
              Connect wallet to create
            </Button>
          ) : (
            <Button
              data-testid="create-submit"
              isLoading={busy}
              showChildrenWhenLoading
              disabled={busy || !question || !conditionValid}
              onClick={create}
            >
              {busy ? "Creating market" : "Create market"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function CustomSourceForm({ onAdd }: { onAdd: (s: SourceDraft) => void }) {
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [from, setFrom] = useState("");

  return (
    <div className="mt-1 flex flex-wrap gap-2">
      <input
        data-testid="custom-source-name"
        placeholder="Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="min-w-32 flex-1 border-2 border-surface-ink bg-paper-0 px-2 py-1.5 text-sm outline-none"
      />
      <input
        data-testid="custom-source-domain"
        placeholder="DKIM domain (e.g. mail.ft.com)"
        value={domain}
        onChange={(e) => setDomain(e.target.value)}
        className="min-w-40 flex-1 border-2 border-surface-ink bg-paper-0 px-2 py-1.5 font-mono text-sm outline-none"
      />
      <input
        data-testid="custom-source-from"
        placeholder="From regex (optional)"
        value={from}
        onChange={(e) => setFrom(e.target.value)}
        className="min-w-40 flex-1 border-2 border-surface-ink bg-paper-0 px-2 py-1.5 font-mono text-sm outline-none"
      />
      <Button
        size="sm"
        variant="secondary"
        data-testid="custom-source-add"
        leftIcon={<Plus size={14} />}
        disabled={!name || !domain}
        onClick={() => {
          onAdd({ name, dkimDomain: domain, fromRegex: from, contentRegex: "" });
          setName("");
          setDomain("");
          setFrom("");
        }}
      >
        Add
      </Button>
    </div>
  );
}
