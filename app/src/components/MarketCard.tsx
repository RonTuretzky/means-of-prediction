import { Link } from "react-router-dom";
import { type MarketData, Resolution } from "../hooks/useMarkets";
import { usePriceHistory } from "../hooks/usePriceHistory";
import { Sparkline } from "./PriceChart";
import { fmtCents, fmtDate, fmtVol } from "../lib/format";
import { ResolutionBadge } from "./RulesPanel";

export function statusBadge(m: MarketData): { label: string; className: string } {
  if (m.resolution === Resolution.Yes) return { label: "Resolved YES", className: "bg-system-green text-white" };
  if (m.resolution === Resolution.No) return { label: "Resolved NO", className: "bg-system-red text-white" };
  if (m.deadline < m.chainNow) return { label: "Ended", className: "bg-surface-grey-2 text-white" };
  return { label: "Live", className: "bg-primary-jade text-white" };
}

export function MarketCard({ m }: { m: MarketData }) {
  const badge = statusBadge(m);
  const { data: history } = usePriceHistory(m);
  const noLiquidity = m.lpSupply === 0n && m.resolution === Resolution.Unresolved;
  const chance =
    m.resolution === Resolution.Yes ? 100 : m.resolution === Resolution.No ? 0 : Math.round(Number(m.priceYes) / 1e16);

  return (
    <Link to={`/market/${m.id}`} data-testid={`market-card-${m.id}`} className="block">
      <div className="bread-card flex h-full flex-col p-4 transition-transform hover:-translate-y-0.5">
        <div className="mb-2 flex items-center gap-2">
          <span className={`px-2 py-0.5 text-caption font-bold uppercase ${badge.className}`}>{badge.label}</span>
          <span className="text-caption text-surface-grey-2">
            {m.matchedCount}/{m.threshold} sources
          </span>
          {m.judged && <ResolutionBadge className="ml-auto" />}
        </div>

        <h3 className="mb-3 min-h-12 font-breadDisplay text-lg font-bold leading-snug">{m.question}</h3>

        {/* hero: % chance + sparkline */}
        <div className="mb-3 flex items-end justify-between">
          <div>
            <div className="font-breadDisplay text-3xl font-black leading-none text-system-green">
              {noLiquidity ? "—" : `${chance}%`}
            </div>
            <div className="text-caption font-bold uppercase text-surface-grey-2">
              {noLiquidity ? "needs liquidity" : "chance"}
            </div>
          </div>
          <Sparkline points={history?.points ?? []} />
        </div>

        <div className="mb-3 flex gap-2">
          <div className="flex-1 border-2 border-system-green bg-[#eaf7e4] px-2 py-1.5 text-center">
            <span className="text-sm font-black text-system-green">Yes {noLiquidity ? "—" : fmtCents(m.priceYes)}</span>
          </div>
          <div className="flex-1 border-2 border-system-red bg-red-0 px-2 py-1.5 text-center">
            <span className="text-sm font-black text-system-red">No {noLiquidity ? "—" : fmtCents(m.priceNo)}</span>
          </div>
        </div>

        <div className="mt-auto flex items-center justify-between text-caption text-surface-grey-2">
          <span>{fmtVol(m.volume, m.collateral.decimals)}</span>
          <span title={m.sources.map((s) => s.name).join(" · ")}>
            {m.sources.length} source{m.sources.length > 1 ? "s" : ""}
          </span>
          <span>Ends {fmtDate(m.deadline)}</span>
        </div>
      </div>
    </Link>
  );
}
