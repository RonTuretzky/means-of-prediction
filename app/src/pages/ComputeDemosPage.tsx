import { Button, Heading1 } from "@breadcoop/ui";
import { ArrowSquareOut, ArrowClockwise, CheckCircle, Clock, WarningCircle } from "@phosphor-icons/react";
import { COMPUTE_DEMOS } from "../data/compute-demos";
import { useComputeDemo } from "../hooks/useComputeDemo";

const SEPOLIA_EXPLORER = "https://sepolia.etherscan.io";
type Demo = (typeof COMPUTE_DEMOS)[number];

function dated(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("en-US", {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC",
  }) + " UTC";
}

function ExplorerLink({ path, children }: { path: string; children: React.ReactNode }) {
  return (
    <a href={`${SEPOLIA_EXPLORER}/${path}`} target="_blank" rel="noopener noreferrer"
      className="inline-flex items-center gap-1 font-bold underline decoration-1 underline-offset-4 hover:text-core-orange focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4"
      aria-label={`${typeof children === "string" ? children : "View on Sepolia Etherscan"} (opens in a new tab)`}>
      {children}<ArrowSquareOut size={14} aria-hidden="true" className="shrink-0" />
    </a>
  );
}

function ComputeDemoCard({ demo }: { demo: Demo }) {
  const query = useComputeDemo(demo);
  const unavailable = query.isError || query.fetchStatus === "paused";
  const checking = !unavailable && (query.isPending || query.isFetching);
  // Hide cached successful reads during errors/refetches, so they cannot appear
  // to verify the current request. The recorded receipt is always separate.
  const live = !checking && !unavailable ? query.data : undefined;
  const matches = live?.outputHash.toLowerCase() === demo.expectedOutputHash.toLowerCase();
  const status = checking ? "Checking Sepolia…"
    : unavailable || !live ? "Live verification unavailable"
      : live.verified ? "Verified on Sepolia" : "Verification mismatch";
  const titleId = `demo-title-${demo.id}`;

  return (
    <article className="bread-card overflow-hidden" aria-labelledby={titleId} data-testid={`compute-demo-${demo.id}`}>
      <div className="border-b-2 border-surface-ink p-4 sm:p-6">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-caption font-bold uppercase">
          <span className="border-2 border-surface-ink bg-paper-1 px-2 py-0.5">Sepolia testnet</span>
          <span className="border-2 border-surface-ink px-2 py-0.5">Arithmetic demo</span>
        </div>
        <h2 id={titleId} className="font-breadDisplay text-2xl font-black leading-tight sm:text-3xl">{demo.title}</h2>
        <p className="mt-2 max-w-3xl text-sm text-surface-grey-2">{demo.description}</p>
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm">
          <ExplorerLink path={`address/${demo.contract}`}>View contract</ExplorerLink>
          <ExplorerLink path={`tx/${demo.settlementTx}`}>View verification transaction</ExplorerLink>
        </div>
      </div>

      <div className="grid gap-0 lg:grid-cols-2">
        <section className="min-w-0 border-b-2 border-surface-ink p-4 sm:p-6 lg:border-b-0 lg:border-r-2" aria-label="Live Sepolia verification">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h3 className="font-breadDisplay text-lg font-bold">Live verification</h3>
            <Button size="sm" variant="light" disabled={checking} onClick={() => void query.refetch()}
              leftIcon={<ArrowClockwise size={16} aria-hidden="true" />} aria-label="Recheck demo on Sepolia" data-testid="compute-demo-recheck">
              {checking ? "Checking" : "Recheck"}
            </Button>
          </div>
          <div role="status" aria-live="polite" aria-atomic="true" className="flex items-center gap-2 font-bold" data-testid="compute-demo-live-status">
            {checking ? <Clock size={20} aria-hidden="true" /> : live?.verified
              ? <CheckCircle size={20} weight="fill" aria-hidden="true" className="text-system-green" />
              : <WarningCircle size={20} aria-hidden="true" className="text-core-orange" />}
            <span>{status}</span>
          </div>
          {checking ? (
            <p className="mt-2 text-sm text-surface-grey-2">Reading the receipt, contract output and verification checks from Sepolia.</p>
          ) : !live ? (
            <p className="mt-2 text-sm text-surface-grey-2">The current check could not complete. The dated recorded result remains available below; recheck to verify it again.</p>
          ) : (
            <>
              <p className="mt-2 text-caption text-surface-grey-2">
                Checked <time dateTime={live.checkedAt}>{dated(live.checkedAt)}</time> · block {live.blockNumber.toLocaleString()}
              </p>
              <dl className="mt-4 grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                <dt className="text-surface-grey-2">Output values</dt><dd className="font-bold">{live.outputCount.toString()} / {demo.expectedOutputCount} expected</dd>
                <dt className="text-surface-grey-2">State transitions</dt><dd className="font-bold">{live.transitionCount.toString()} / {demo.expectedTransitionCount} expected</dd>
                <dt className="text-surface-grey-2">Receipt gas used</dt><dd>{live.gasUsed.toLocaleString()}</dd>
                <dt className="text-surface-grey-2">Projected events</dt><dd>{live.eventCount}</dd>
              </dl>
              <p className="mt-4 text-caption font-bold uppercase text-surface-grey-2">On-chain output hash</p>
              <code className="mt-1 block break-all border-2 border-surface-ink bg-paper-1 p-2 text-xs" data-testid="compute-demo-output-hash">{live.outputHash}</code>
              <p className="mt-2 flex items-center gap-1.5 text-sm font-bold">
                {matches ? <CheckCircle size={16} aria-hidden="true" /> : <WarningCircle size={16} aria-hidden="true" />}
                {matches ? "Matches the expected output hash" : "Does not match the expected output hash"}
              </p>
              {!live.verified && <p className="mt-2 text-sm">At least one verification check failed. Inspect the checklist below before relying on this result.</p>}
            </>
          )}
        </section>

        <section className="min-w-0 bg-paper-1 p-4 sm:p-6" aria-label="Dated recorded result">
          <h3 className="font-breadDisplay text-lg font-bold">Recorded result</h3>
          <p className="mt-1 text-caption text-surface-grey-2">
            Snapshot saved <time dateTime={demo.recordedAt}>{dated(demo.recordedAt)}</time>. This is not a live check.
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
            <dt className="text-surface-grey-2">Receipt block</dt><dd><ExplorerLink path={`block/${demo.settlementBlock}`}>{BigInt(demo.settlementBlock).toLocaleString()}</ExplorerLink></dd>
            <dt className="text-surface-grey-2">Recorded readback block</dt><dd>{BigInt(demo.recordedBlock).toLocaleString()}</dd>
            <dt className="text-surface-grey-2">Receipt gas used</dt><dd>{BigInt(demo.recordedGasUsed).toLocaleString()}</dd>
            <dt className="text-surface-grey-2">Recorded output</dt><dd className="font-bold">{demo.expectedOutputCount} values · {demo.expectedTransitionCount} transition</dd>
          </dl>
          <p className="mt-4 text-caption font-bold uppercase text-surface-grey-2">Expected output hash</p>
          <code className="mt-1 block break-all border-2 border-surface-ink bg-paper-0 p-2 text-xs">{demo.expectedOutputHash}</code>
          <ol className="mt-5 space-y-4" aria-label="Recorded demo timeline">
            {[
              ["Prepared", "Fixed input and weights were committed before execution."],
              ["Operator certificate", "Gas Killer operators attested to the calculated output."],
              ["Public Sepolia receipt", "The contract accepted the certificate and stored the output hash."],
            ].map(([title, description], index) => (
              <li key={title} className="flex gap-3 text-sm">
                <span aria-hidden="true" className="flex h-6 w-6 shrink-0 items-center justify-center border-2 border-surface-ink bg-paper-0 font-bold">{index + 1}</span>
                <div><p className="font-bold">{title}</p><p className="text-surface-grey-2">{description}</p></div>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <div className="border-t-2 border-surface-ink p-4 sm:p-6">
        <p className="text-sm"><b>What this demonstrates:</b> one arithmetic component: 32 of 3,072 layer-0 outputs from a fixed initial token. Full-model execution and prediction-market settlement are still unfinished. The certificate is an operator attestation; it does not prove the truth of news.</p>
        <details className="mt-4 border-t-2 border-surface-ink pt-3" data-testid="compute-demo-details">
          <summary className="cursor-pointer font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4">Verification checks and pinned inputs</summary>
          <div className="mt-4 grid gap-5 lg:grid-cols-2">
            <section aria-label="Verification checklist">
              <h4 className="mb-2 text-caption font-bold uppercase text-surface-grey-2">Current verification checklist</h4>
              {live ? <ul className="space-y-2 text-sm">{live.checks.map((check, index) => (
                <li key={`${check.label}-${index}`} className="flex items-start gap-2">
                  {check.passed ? <CheckCircle size={18} aria-hidden="true" className="mt-0.5 shrink-0" /> : <WarningCircle size={18} aria-hidden="true" className="mt-0.5 shrink-0" />}
                  <span><b>{check.passed ? "Pass" : "Fail"}:</b> {check.label}</span>
                </li>
              ))}</ul> : <p className="text-sm text-surface-grey-2">{checking ? "Checks are running." : "Live verification unavailable. Recheck to load the checklist."}</p>}
            </section>
            <dl className="min-w-0 space-y-3 text-xs">
              {[
                ["Model SHA-256", demo.modelHash], ["Runtime SHA-256", demo.runtimeHash], ["Export SHA-256", demo.exportHash],
                ["Input SHA-256", demo.inputHash], ["Weights SHA-256", demo.weightsHash], ["Shifts SHA-256", demo.shiftsHash],
                ["Deployed bytecode hash", demo.runtimeCodeHash], ["AVS", demo.avs], ["Operator registry", demo.registry],
                ["Gas Killer task", demo.taskId], ["Contract", demo.contract], ["Chain ID", String(demo.chainId)],
              ].map(([label, value]) => <div key={label}><dt className="font-bold text-surface-grey-2">{label}</dt><dd className="mt-0.5 break-all font-mono">{value}</dd></div>)}
              <div><dt className="mb-1 font-bold text-surface-grey-2">Public transactions</dt><dd className="flex flex-wrap gap-x-4 gap-y-2"><ExplorerLink path={`tx/${demo.deploymentTx}`}>Deployment</ExplorerLink><ExplorerLink path={`tx/${demo.settlementTx}`}>Verification</ExplorerLink></dd></div>
            </dl>
          </div>
        </details>
      </div>
    </article>
  );
}

export function ComputeDemosPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <Heading1>Compute demos</Heading1>
      <p className="mb-6 mt-2 max-w-3xl text-body text-surface-grey-2">Inspect a model calculation recorded on Sepolia. Verification is read-only, always uses Sepolia, and needs no wallet—even if your market network is Gnosis.</p>
      <div className="space-y-6">{COMPUTE_DEMOS.map(demo => <ComputeDemoCard key={demo.id} demo={demo} />)}</div>
    </div>
  );
}
