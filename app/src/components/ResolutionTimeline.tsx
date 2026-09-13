import { Check, Circle, Envelope, Flag, HourglassMedium, Lock } from "@phosphor-icons/react";
import { Resolution, type MarketData } from "../hooks/useMarkets";
import { fmtDate, fmtDuration } from "../lib/format";

// Polymarket shows resolution as a labeled timeline ("Outcome proposed → Dispute
// window → Final outcome"). Ours is the DKIM equivalent: opened → proofs 1..K →
// threshold → resolved / NO-window.
interface Step {
  icon: React.ReactNode;
  label: string;
  detail?: string;
  state: "done" | "current" | "pending";
}

export function ResolutionTimeline({ m }: { m: MarketData }) {
  const now = Number(m.chainNow);
  const noAt = Number(m.deadline) + Number(m.resolutionBuffer);
  const steps: Step[] = [];

  steps.push({
    icon: <Flag size={14} weight="bold" />,
    label: "Market opened",
    detail: fmtDate(m.createdAt),
    state: "done",
  });

  const proofs = [...m.evidence].sort((a, b) => Number(a.emailTimestamp - b.emailTimestamp));
  proofs.forEach((ev, i) => {
    steps.push({
      icon: <Envelope size={14} weight="bold" />,
      label: `Proof ${i + 1} of ${m.threshold} — ${m.sources[ev.sourceIndex]?.name ?? "?"}`,
      detail: `“${ev.subject}”`,
      state: "done",
    });
  });

  if (m.resolution === Resolution.Yes) {
    steps.push({
      icon: <Check size={14} weight="bold" />,
      label: "Resolved YES",
      detail: "threshold reached — winning shares redeem at $1.00",
      state: "done",
    });
  } else if (m.resolution === Resolution.No) {
    steps.push({
      icon: <Lock size={14} weight="bold" />,
      label: "Resolved NO",
      detail: "deadline passed without enough matching alerts",
      state: "done",
    });
  } else {
    if (m.matchedCount < m.threshold) {
      steps.push({
        icon: <Envelope size={14} weight="bold" />,
        label: `Waiting for ${m.threshold - m.matchedCount} more source${m.threshold - m.matchedCount > 1 ? "s" : ""}`,
        detail: "anyone can submit a DKIM proof below",
        state: "current",
      });
    }
    steps.push({
      icon: <HourglassMedium size={14} weight="bold" />,
      label: now > noAt ? "NO can be resolved now" : `NO resolvable in ${fmtDuration(noAt - now)}`,
      detail: `deadline ${fmtDate(m.deadline)} + ${Number(m.resolutionBuffer) / 3600}h buffer`,
      state: now > noAt ? "current" : "pending",
    });
  }

  return (
    <ol className="relative ml-2 border-l-2 border-surface-ink pl-5" data-testid="resolution-timeline">
      {steps.map((s, i) => (
        <li key={i} className={`relative pb-3 ${s.state === "pending" ? "opacity-50" : ""}`}>
          <span
            className={`absolute -left-[27px] top-0 flex h-6 w-6 items-center justify-center border-2 border-surface-ink ${
              s.state === "done"
                ? "bg-system-green text-white"
                : s.state === "current"
                  ? "bg-core-orange text-white"
                  : "bg-paper-0 text-surface-grey-2"
            }`}
          >
            {s.state === "pending" ? <Circle size={10} /> : s.icon}
          </span>
          <div className="text-sm font-bold leading-6">{s.label}</div>
          {s.detail && <div className="text-caption text-surface-grey-2">{s.detail}</div>}
        </li>
      ))}
    </ol>
  );
}
