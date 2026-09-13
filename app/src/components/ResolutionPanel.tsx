import { useState } from "react";
import { Button, Chip } from "@breadcoop/ui";
import { CheckCircle, Circle, EnvelopeSimple, SealCheck, UploadSimple } from "@phosphor-icons/react";
import { zeroAddress, zeroHash, keccak256, encodeFunctionData, type Hex, type Address } from "viem";
import { abis } from "../contracts/gen";
import { Resolution, type MarketData } from "../hooks/useMarkets";
import { resolveKey, useDkimKeys } from "../hooks/useDkimKeys";
import { fmtDate, fmtDuration } from "../lib/format";
import { settlementAbi } from "../lib/settlement-abi";
import { BODY_PARSING, deployment } from "../config";
import { bodyPages } from "../lib/body-transport";
import { bytesLatin1 } from "../lib/body";
import { buildEmailProof, parseEml, type EmailProofStruct, type ParsedEmail } from "../lib/prover";
import { publicClient, useWallet } from "../lib/wallet";
import { useToast } from "./Toast";
import { JUDGE_MODEL, JUDGE_TRUST_LINE } from "./RulesPanel";
import { explain } from "./TradeWidget";

interface Candidate {
  paginated?: boolean;
  parsed: ParsedEmail;
  proof: EmailProofStruct | null;
  sourceIndex: number | null; // the market source whose domain matches (domains are unique)
  keyKnown: boolean; // is this email's DKIM key registered onchain?
  checked: { ok: boolean; reason: string } | null;
  /** Judged markets only: the prompt key + exact subject the judge sees, and its verdict. */
  judged: JudgedState | null;
}

interface JudgedState {
  key: Hex;
  subject: string; // decoded from the RSA-signed header (what the judge is shown)
  ok: boolean; // false = subject unreadable / contains control strings -> never judgeable
  verdict: 0 | 1 | 2; // ILLMJudge.Verdict: None | Yes | No
}

const VERDICT_LABEL: Record<JudgedState["verdict"], string> = { 0: "not judged yet", 1: "YES", 2: "NO" };

/** For judged markets: the prompt key the judge must answer for this email and its verdict so far. */
async function fetchJudged(m: MarketData, proof: EmailProofStruct): Promise<JudgedState> {
  const [key, subjectBytes, ok] = (await publicClient.readContract({
    address: m.market,
    abi: settlementAbi,
    functionName: "promptKeyFor",
    args: [proof],
  })) as [Hex, Hex, boolean];
  const subject = new TextDecoder().decode(hexToBytes(subjectBytes));
  if (!ok || m.judge === zeroAddress) return { key: zeroHash, subject, ok: false, verdict: 0 };
  const verdict = (await publicClient.readContract({
    address: m.judge,
    abi: abis.LLMJudge,
    functionName: "verdictOf",
    args: [key],
  })) as number;
  return { key, subject, ok: true, verdict: (verdict === 1 ? 1 : verdict === 2 ? 2 : 0) as JudgedState["verdict"] };
}

function hexToBytes(hex: Hex): Uint8Array {
  const h = hex.slice(2);
  const out = new Uint8Array(h.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(h.slice(i * 2, i * 2 + 2), 16);
  return out;
}

export function ResolutionPanel({ m }: { m: MarketData }) {
  const wallet = useWallet();
  const toast = useToast();
  const { data: keys, refetch: refreshKeys } = useDkimKeys();
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [txError, setTxError] = useState<string | null>(null);

  const now = Number(m.chainNow);
  const noResolvableAt = Number(m.deadline) + Number(m.resolutionBuffer);
  const open = m.resolution === Resolution.Unresolved;

  const onFile = async (file: File) => {
    setFileError(null);
    setTxError(null);
    setCandidate(null);
    try {
      const parsed = parseEml(bytesLatin1(new Uint8Array(await file.arrayBuffer())));
      const sourceIndex = m.sources.findIndex((s) => s.dkimDomain === parsed.domain);
      const availableKeys = keys ?? (await refreshKeys()).data;
      if (!availableKeys) throw new Error("Could not load registered DKIM keys; retry the email upload");
      const publicKeyHash = resolveKey(availableKeys, parsed.domain, parsed.selector);
      if (sourceIndex < 0 || !publicKeyHash) {
        setCandidate({
          parsed,
          proof: null,
          sourceIndex: sourceIndex >= 0 ? sourceIndex : null,
          keyKnown: !!publicKeyHash,
          checked: null,
          judged: null,
        });
        return;
      }
      const proof = buildEmailProof(parsed, publicKeyHash, { contentField: BODY_PARSING ? m.contentField : 0, pattern: m.sources[sourceIndex].contentRegex || m.contentRegex });
      const calldata = encodeFunctionData({ abi: settlementAbi, functionName: "submitProof", args: [BigInt(sourceIndex), proof] });
      const paginated = (calldata.length - 2) / 2 + 200 > 128 * 1024;
      if (paginated && !deployment.emailBodyStore) {
        setCandidate({ parsed, proof, sourceIndex, keyKnown: true, checked: { ok: false, reason: "This proof exceeds the common 128 KiB transaction relay limit. This deployment has no paginated body store; choose a smaller email or a deployment with body pagination." }, judged: null });
        return;
      }
      const [ok, reason] = (await publicClient.readContract({
        address: m.market,
        abi: settlementAbi,
        functionName: "checkProof",
        args: [BigInt(sourceIndex), proof],
      })) as [boolean, string];
      const judged = m.judged ? await fetchJudged(m, proof) : null;
      setCandidate({ parsed, proof, sourceIndex, keyKnown: true, checked: { ok, reason }, judged, paginated });
    } catch (e) {
      setFileError(explain(e));
    }
  };

  const submitProof = async () => {
    if (!candidate?.proof || candidate.sourceIndex === null) return;
    setBusy("proof");
    setTxError(null);
    try {
      if (candidate.paginated && deployment.emailBodyStore) {
        const address = deployment.emailBodyStore as Address;
        const pages = bodyPages(candidate.proof.canonicalBody);
        const pointers: Address[] = [];
        for (const [i, page] of pages.entries()) {
          setUploadProgress(`Uploading body part ${i + 1} of ${pages.length}`);
          const hash = keccak256(page);
          let pointer = await publicClient.readContract({ address, abi: abis.EmailBodyStore, functionName: "chunkForHash", args: [hash] });
          if (pointer === zeroAddress) {
            await wallet.write({ address, abi: abis.EmailBodyStore, functionName: "storeChunk", args: [page] });
            pointer = await publicClient.readContract({ address, abi: abis.EmailBodyStore, functionName: "chunkForHash", args: [hash] });
          }
          if (pointer === zeroAddress) throw new Error("Body part is not confirmed yet; retry to resume");
          pointers.push(pointer);
        }
        setUploadProgress("Verifying all parts and settling");
        await wallet.write({ address, abi: abis.EmailBodyStore, functionName: "submitWithChunks", args: [m.market, BigInt(candidate.sourceIndex), { ...candidate.proof, canonicalBody: "0x" }, pointers] });
      } else {
        setUploadProgress("Verifying onchain");
        await wallet.write({ address: m.market, abi: settlementAbi, functionName: "submitProof", args: [BigInt(candidate.sourceIndex), candidate.proof] });
      }
      toast.push({
        kind: "success",
        title: `Proof accepted — ${m.sources[candidate.sourceIndex].name}`,
        detail: "real DKIM signature verified onchain",
      });
      setCandidate(null);
    } catch (e) {
      setTxError(explain(e));
    } finally {
      setBusy(null);
    }
  };

  const resolveNo = async () => {
    setBusy("no");
    setTxError(null);
    try {
      await wallet.write({ address: m.market, abi: settlementAbi, functionName: "resolveNo" });
      toast.push({ kind: "success", title: "Resolved NO", detail: m.question });
    } catch (e) {
      setTxError(explain(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div data-testid="resolution-panel">
      <p className="mb-3 text-sm text-surface-grey-2">
        Anyone can settle this market by uploading a real DKIM-signed alert email — its RSA signature is verified
        onchain against the newspaper's published key. {m.threshold} of {m.sources.length} sources required for YES.
        {m.judged && (
          <>
            {" "}
            Whether an alert counts is decided by the on-chain judge ({JUDGE_MODEL} via Gas Killer), not a regex:
            the email settles only once the judge holds a YES verdict for its exact subject line.
          </>
        )}
      </p>

      <ul className="mb-4 space-y-2" data-testid="source-status">
        {m.sources.map((s, i) => {
          const ev = m.evidence.find((e) => e.sourceIndex === i);
          return (
            <li key={i} className="flex items-start gap-2 text-sm">
              {m.sourceMatched[i] ? (
                <CheckCircle size={18} weight="fill" className="mt-0.5 shrink-0 text-system-green" />
              ) : (
                <Circle size={18} className="mt-0.5 shrink-0 text-surface-grey" />
              )}
              <div>
                <span className="font-bold">{s.name}</span>{" "}
                <span className="text-caption text-surface-grey-2">({s.dkimDomain})</span>
                {ev && (
                  <div className="text-caption text-surface-grey-2">
                    “{ev.subject}” · {fmtDate(ev.emailTimestamp)} · by {short(ev.submitter)}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {m.resolution === Resolution.Yes && (
        <div className="border-2 border-system-green bg-[#eaf7e4] p-3 font-bold text-system-green">
          Resolved YES — threshold reached.
        </div>
      )}
      {m.resolution === Resolution.No && (
        <div className="border-2 border-system-red bg-red-0 p-3 font-bold text-system-red">
          Resolved NO — deadline passed without enough matching alerts.
        </div>
      )}

      {open && (
        <>
          <label
            className="flex cursor-pointer items-center justify-center gap-2 border-2 border-dashed border-surface-ink bg-paper-1 px-3 py-6 text-center font-bold transition-colors hover:border-core-orange hover:bg-paper-2"
            data-testid="eml-drop"
          >
            <UploadSimple size={20} />
            Upload a raw email (.eml) to verify its DKIM signature
            <input
              type="file"
              accept=".eml,message/rfc822,text/plain"
              className="hidden"
              data-testid="eml-input"
              disabled={!!busy}
              onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
            />
          </label>
          <p className="mt-1 text-caption text-surface-grey-2">
            In Gmail: open the alert → ⋮ → “Show original” → Download original. The real RSA-SHA256 DKIM signature
            is verified onchain against the domain's registered public key.
          </p>

          {fileError && (
            <div className="mt-2 border-2 border-system-red bg-red-0 px-2 py-1 text-caption text-system-red">
              {fileError}
            </div>
          )}

          {candidate && (
            <div className="mt-3 border-2 border-surface-ink bg-paper-0 p-3" data-testid="proof-preview">
              <div className="mb-2 flex items-center gap-2 font-bold">
                <EnvelopeSimple size={18} /> Email proof preview
              </div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                <dt className="text-surface-grey-2">Signing domain</dt>
                <dd className="font-mono">
                  {candidate.parsed.domain}{" "}
                  <span className="text-surface-grey-2">(s={candidate.parsed.selector})</span>
                </dd>
                <dt className="text-surface-grey-2">From</dt>
                <dd className="font-mono">{candidate.parsed.fromAddress}</dd>
                <dt className="text-surface-grey-2">Subject</dt>
                <dd data-testid="proof-subject">{candidate.parsed.subjectDisplay}</dd>
                <dt className="text-surface-grey-2">Date</dt>
                <dd>{fmtDate(candidate.parsed.timestamp)}</dd>
                <dt className="text-surface-grey-2">RSA signature</dt>
                <dd className="text-caption">
                  {candidate.parsed.signature.length * 8}-bit · nullifier {short(candidate.parsed.nullifier)}
                </dd>
              </dl>

              {candidate.proof && candidate.proof.bodyLength > 0n && (
                <div className="mt-3 text-sm">
                  <b>Authenticated body source</b>
                  <p>The full canonical body becomes public onchain. The contract checks its signed hash and decodes this excerpt. HTML markup is retained as text.</p>
                  <pre data-testid="proof-body" className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all border p-2 text-xs">{candidate.proof.bodyExcerpt}</pre>
                </div>
              )}
              {candidate.paginated && deployment.emailBodyStore && candidate.proof && (
                <p data-testid="body-pagination" className="mt-2 border-2 border-surface-ink p-2 text-sm">
                  This email needs {bodyPages(candidate.proof.canonicalBody).length} body uploads, then one settlement transaction.
                  Each upload costs gas and permanently publishes part of the email. Already uploaded parts are reused if you retry.
                  Pagination fits the transaction size limit and adds to total cost.
                </p>
              )}
              {candidate.judged && (
                <div className="mt-2 border-2 border-surface-ink bg-paper-1 p-2 text-sm" data-testid="judge-status">
                  <div className="font-bold">
                    Verdict:{" "}
                    <span
                      data-testid="judge-verdict"
                      className={
                        candidate.judged.verdict === 1
                          ? "text-system-green"
                          : candidate.judged.verdict === 2
                            ? "text-system-red"
                            : "text-surface-grey-2"
                      }
                    >
                      {candidate.judged.ok ? VERDICT_LABEL[candidate.judged.verdict] : "not judgeable"}
                    </span>
                  </div>
                  {!candidate.judged.ok ? (
                    <p className="mt-1 text-caption text-surface-grey-2">
                      The signed header's Subject could not be read safely (missing, over 400 bytes, or containing
                      chat-template control strings), so the judge will never issue a verdict for this email.
                    </p>
                  ) : candidate.judged.verdict === 0 ? (
                    <p className="mt-1 text-caption text-surface-grey-2">
                      Not judged yet. A settlement bot holding a Gas Killer API key must request the verdict
                      (<code>settlement-bot.mjs</code> with <code>GK_API_KEY</code>): it sends the judge call for this
                      prompt key to the Gas Killer router, the operator set runs {JUDGE_MODEL} over the prompt and
                      signs the result, and the bot submits that attestation on-chain. Once the judge holds a YES
                      verdict, anyone can submit this email.
                    </p>
                  ) : candidate.judged.verdict === 2 ? (
                    <p className="mt-1 text-caption text-surface-grey-2">
                      The judge ruled this subject line does not satisfy the rules; it is not evidence for this market.
                    </p>
                  ) : null}
                  <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-caption">
                    <dt className="text-surface-grey-2">Subject the judge sees</dt>
                    <dd data-testid="judge-subject" className="break-words">
                      “{candidate.judged.subject}”
                    </dd>
                    {candidate.judged.ok && (
                      <>
                        <dt className="text-surface-grey-2">Prompt key</dt>
                        <dd data-testid="judge-key" className="break-all font-mono">
                          {candidate.judged.key}
                        </dd>
                      </>
                    )}
                    <dt className="text-surface-grey-2">Judge</dt>
                    <dd className="break-all font-mono">{m.judge}</dd>
                  </dl>
                  <p className="mt-1 text-caption text-surface-grey-2">{JUDGE_TRUST_LINE}</p>
                </div>
              )}

              <div className="mt-2">
                {candidate.sourceIndex === null ? (
                  <Chip>No market source uses domain “{candidate.parsed.domain}”</Chip>
                ) : !candidate.keyKnown ? (
                  <Chip>
                    DKIM key for {candidate.parsed.domain} (s={candidate.parsed.selector}) not registered onchain
                  </Chip>
                ) : candidate.checked?.ok ? (
                  <div className="flex items-center gap-1 font-bold text-system-green" data-testid="proof-check-ok">
                    <SealCheck size={16} weight="fill" /> Valid DKIM signature — settles{" "}
                    {m.sources[candidate.sourceIndex].name}
                  </div>
                ) : (
                  <div className="font-bold text-system-red" data-testid="proof-check-fail">
                    ✗ Rejected: {candidate.checked?.reason}
                  </div>
                )}
              </div>

              <Button
                data-testid="submit-proof"
                className="mt-3 w-full"
                disabled={!candidate.checked?.ok || !!busy}
                isLoading={busy === "proof"}
                showChildrenWhenLoading
                onClick={submitProof}
              >
                {busy === "proof" ? uploadProgress : candidate.paginated ? "Upload body parts & settle" : "Submit proof & settle"}
              </Button>
            </div>
          )}

          <div className="mt-4 border-t-2 border-surface-ink pt-3">
            {now > noResolvableAt ? (
              <Button
                data-testid="resolve-no"
                variant="destructive"
                className="w-full"
                disabled={!!busy}
                isLoading={busy === "no"}
                showChildrenWhenLoading
                onClick={resolveNo}
              >
                {busy === "no" ? "Resolving NO" : "Resolve NO (deadline passed)"}
              </Button>
            ) : (
              <p className="text-caption text-surface-grey-2">
                If the threshold isn't reached, anyone can resolve NO in {fmtDuration(noResolvableAt - now)} (deadline{" "}
                {fmtDate(m.deadline)} + {Number(m.resolutionBuffer) / 3600}h buffer).
              </p>
            )}
          </div>
        </>
      )}

      {txError && (
        <div className="mt-2 border-2 border-system-red bg-red-0 px-2 py-1 text-caption text-system-red">{txError}</div>
      )}
    </div>
  );
}

function short(a: string): string {
  return `${a.slice(0, 6)}…${a.slice(-4)}`;
}
