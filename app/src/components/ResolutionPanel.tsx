import { useState } from "react";
import { Button, Chip } from "@breadcoop/ui";
import { CheckCircle, Circle, EnvelopeSimple, SealCheck, UploadSimple } from "@phosphor-icons/react";
import { abis } from "../contracts/gen";
import { Resolution, type MarketData } from "../hooks/useMarkets";
import { resolveKey, useDkimKeys } from "../hooks/useDkimKeys";
import { fmtDate, fmtDuration } from "../lib/format";
import { buildEmailProof, parseEml, type EmailProofStruct, type ParsedEmail } from "../lib/prover";
import { publicClient, useWallet } from "../lib/wallet";
import { useToast } from "./Toast";
import { explain } from "./TradeWidget";

interface Candidate {
  parsed: ParsedEmail;
  proof: EmailProofStruct | null;
  sourceIndex: number | null; // the market source whose domain matches (domains are unique)
  keyKnown: boolean; // is this email's DKIM key registered onchain?
  checked: { ok: boolean; reason: string } | null;
}

export function ResolutionPanel({ m }: { m: MarketData }) {
  const wallet = useWallet();
  const toast = useToast();
  const { data: keys } = useDkimKeys();
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
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
      const parsed = parseEml(await file.text());
      const sourceIndex = m.sources.findIndex((s) => s.dkimDomain === parsed.domain);
      const publicKeyHash = resolveKey(keys, parsed.domain, parsed.selector);
      if (sourceIndex < 0 || !publicKeyHash) {
        setCandidate({
          parsed,
          proof: null,
          sourceIndex: sourceIndex >= 0 ? sourceIndex : null,
          keyKnown: !!publicKeyHash,
          checked: null,
        });
        return;
      }
      const proof = buildEmailProof(parsed, publicKeyHash);
      const [ok, reason] = (await publicClient.readContract({
        address: m.market,
        abi: abis.HeadlineMarket,
        functionName: "checkProof",
        args: [BigInt(sourceIndex), proof],
      })) as [boolean, string];
      setCandidate({ parsed, proof, sourceIndex, keyKnown: true, checked: { ok, reason } });
    } catch (e) {
      setFileError(explain(e));
    }
  };

  const submitProof = async () => {
    if (!candidate?.proof || candidate.sourceIndex === null) return;
    setBusy("proof");
    setTxError(null);
    try {
      await wallet.write({
        address: m.market,
        abi: abis.HeadlineMarket,
        functionName: "submitProof",
        args: [BigInt(candidate.sourceIndex), candidate.proof],
      });
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
      await wallet.write({ address: m.market, abi: abis.HeadlineMarket, functionName: "resolveNo" });
      toast.push({ kind: "success", title: "Resolved NO", detail: m.question });
    } catch (e) {
      setTxError(explain(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div data-testid="resolution-panel" data-dkim-keys-ready={keys !== undefined}>
      <p className="mb-3 text-sm text-surface-grey-2">
        Anyone can settle this market by uploading a real DKIM-signed alert email — its RSA signature is verified
        onchain against the newspaper's published key. {m.threshold} of {m.sources.length} sources required for YES.
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
                <EnvelopeSimple size={18} /> DKIM-verified email
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
                {busy === "proof" ? "Verifying onchain" : "Submit proof & settle"}
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
