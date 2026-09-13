import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Chip } from "@breadcoop/ui";
import { ArrowLeft, CaretDown, CaretUp } from "@phosphor-icons/react";
import { statusBadge } from "../components/MarketCard";
import { ActivityFeed } from "../components/ActivityFeed";
import { LiquidityPanel } from "../components/LiquidityPanel";
import { ProtocolFeesPanel } from "../components/ProtocolFeesPanel";
import { PositionsPanel } from "../components/PositionsPanel";
import { PriceChart } from "../components/PriceChart";
import { ResolutionPanel } from "../components/ResolutionPanel";
import { ResolutionTimeline } from "../components/ResolutionTimeline";
import { ResolutionBadge, RulesPanel } from "../components/RulesPanel";
import { MarketPageSkeleton } from "../components/Skeleton";
import { TradeWidget } from "../components/TradeWidget";
import { Resolution, useMarket } from "../hooks/useMarkets";
import { usePriceHistory } from "../hooks/usePriceHistory";
import { fmtCents, fmtChance, fmtDate, fmtVol } from "../lib/format";

type Tab = "resolution" | "activity" | "rules";

export function MarketPage() {
  const { id } = useParams();
  const { data: m, isLoading } = useMarket(Number(id));
  const { data: history } = usePriceHistory(m);
  const [tab, setTab] = useState<Tab>("resolution");

  if (isLoading) return <MarketPageSkeleton />;
  if (!m)
    return (
      <div className="mx-auto max-w-6xl px-4 py-8">
        <p className="font-bold">Oops… we didn't forecast this. Market not found.</p>
        <Link to="/" className="text-core-orange underline">
          Back to markets
        </Link>
      </div>
    );

  const badge = statusBadge(m);
  const headline = m.resolution === Resolution.Yes ? 10n ** 18n : m.resolution === Resolution.No ? 0n : m.priceYes;
  const points = history?.points ?? [];
  // 24h-style delta: current vs first point in the last day (or series start)
  const dayAgo = Number(m.chainNow) - 86400;
  const ref = points.find((p) => p.ts >= dayAgo) ?? points[0];
  const cur = Number(headline) / 1e18;
  const delta = ref ? Math.round((cur - ref.price) * 100) : 0;

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <Link
        to="/"
        className="mb-4 inline-flex items-center gap-1 text-sm font-bold text-surface-grey-2 hover:text-core-orange"
      >
        <ArrowLeft size={14} /> All markets
      </Link>

      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <div className="mb-2 flex items-center gap-2">
            <span className={`px-2 py-0.5 text-caption font-bold uppercase ${badge.className}`}>{badge.label}</span>
            <Chip size="small">
              {m.matchedCount}/{m.threshold} sources matched
            </Chip>
            {m.judged && <ResolutionBadge />}
          </div>
          <h1 className="font-breadDisplay text-3xl font-black leading-tight" data-testid="market-question">
            {m.question}
          </h1>
          <div className="mt-2 flex flex-wrap gap-4 text-sm text-surface-grey-2">
            <span>{fmtVol(m.volume, m.collateral.decimals)}</span>
            <span>Ends {fmtDate(m.deadline)}</span>
            <span>Collateral: {m.collateral.symbol}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="font-breadDisplay text-5xl font-black text-system-green" data-testid="headline-price">
            {fmtCents(headline)}
          </div>
          <div className="flex items-center justify-end gap-1 text-sm font-bold text-surface-grey-2">
            {fmtChance(headline)}
            {m.resolution === Resolution.Unresolved && delta !== 0 && (
              <span className={`flex items-center ${delta > 0 ? "text-system-green" : "text-system-red"}`}>
                {delta > 0 ? <CaretUp size={12} weight="bold" /> : <CaretDown size={12} weight="bold" />}
                {Math.abs(delta)}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <PriceChart points={points} now={Number(m.chainNow)} />

          <div className="bread-card p-4">
            <div className="mb-3 flex border-2 border-surface-ink">
              {(
                [
                  ["resolution", "Resolution"],
                  ["activity", "Activity"],
                  ["rules", "Rules"],
                ] as [Tab, string][]
              ).map(([t, label]) => (
                <button
                  key={t}
                  data-testid={`market-tab-${t}`}
                  onClick={() => setTab(t)}
                  className={`flex-1 px-3 py-2 font-breadDisplay font-bold uppercase ${
                    tab === t ? "bg-surface-ink text-paper-0" : "bg-paper-0 text-surface-ink"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            {tab === "resolution" && (
              <div className="space-y-4">
                <ResolutionTimeline m={m} />
                <ResolutionPanel m={m} />
              </div>
            )}
            {tab === "activity" && <ActivityFeed m={m} activity={history?.activity ?? []} />}
            {tab === "rules" && <RulesPanel m={m} />}
          </div>

          <LiquidityPanel m={m} />
          <ProtocolFeesPanel m={m} />
        </div>
        <div className="space-y-6">
          <TradeWidget m={m} />
          <PositionsPanel m={m} />
        </div>
      </div>
    </div>
  );
}
