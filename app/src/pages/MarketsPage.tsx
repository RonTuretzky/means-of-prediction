import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Button, Heading1 } from "@breadcoop/ui";
import { MarketCard } from "../components/MarketCard";
import { MarketCardSkeleton } from "../components/Skeleton";
import { Resolution, useMarkets } from "../hooks/useMarkets";
import { CATEGORIES, parseCategory, type Category } from "../data/categories";
import { CHAIN_LABEL, IS_LOCAL } from "../config";

type Sort = "newest" | "volume" | "liquidity" | "ending";
type Filter = "all" | "live" | "resolved";

export function MarketsPage() {
  const { data: markets, isLoading, error } = useMarkets();
  const [sort, setSort] = useState<Sort>("newest");
  const [filter, setFilter] = useState<Filter>("all");
  const [cat, setCat] = useState<Category | "all">("all");
  const [q, setQ] = useState("");

  const shown = useMemo(() => {
    if (!markets) return [];
    let list = [...markets];
    if (filter === "live") list = list.filter((m) => m.resolution === Resolution.Unresolved);
    if (filter === "resolved") list = list.filter((m) => m.resolution !== Resolution.Unresolved);
    if (cat !== "all") list = list.filter((m) => parseCategory(m.description) === cat);
    if (q.trim()) {
      const needle = q.toLowerCase();
      list = list.filter(
        (m) =>
          m.question.toLowerCase().includes(needle) ||
          m.sources.some((s) => s.name.toLowerCase().includes(needle)),
      );
    }
    const cmp: Record<Sort, (a: typeof list[0], b: typeof list[0]) => number> = {
      newest: (a, b) => Number(b.createdAt - a.createdAt),
      volume: (a, b) => Number(b.volume - a.volume),
      liquidity: (a, b) => Number(b.poolYes + b.poolNo - (a.poolYes + a.poolNo)),
      ending: (a, b) => Number(a.deadline - b.deadline),
    };
    return list.sort(cmp[sort]);
  }, [markets, sort, filter, cat, q]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <Heading1>Markets</Heading1>
          <p className="max-w-2xl text-body text-surface-grey-2">
            Settled by the newspapers themselves. Anyone can open a market over any set of newspapers
            and any headline condition; anyone can settle one by submitting a DKIM-signed
            breaking-news alert. <Link to="/" className="font-semibold text-core-orange underline">How it works →</Link>
          </p>
        </div>
        <Link to="/create">
          <Button data-testid="nav-create">Create market</Button>
        </Link>
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5" data-testid="category-tabs">
        {(["all", ...CATEGORIES] as const).map((c) => (
          <button
            key={c}
            data-testid={`cat-${c}`}
            onClick={() => setCat(c as Category | "all")}
            className={`border-2 px-2.5 py-1 text-sm font-bold uppercase ${
              cat === c ? "border-core-orange bg-[#FBDED1] text-core-orange" : "border-surface-ink bg-paper-0"
            }`}
          >
            {c === "all" ? "All" : c}
          </button>
        ))}
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input
          data-testid="search"
          placeholder="Search markets…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="min-w-56 flex-1 border-2 border-surface-ink bg-paper-0 px-3 py-2 outline-none focus:border-core-orange"
        />
        <div className="flex border-2 border-surface-ink">
          {(["all", "live", "resolved"] as Filter[]).map((f) => (
            <button
              key={f}
              data-testid={`filter-${f}`}
              onClick={() => setFilter(f)}
              className={`px-3 py-2 text-sm font-bold uppercase ${
                filter === f ? "bg-surface-ink text-paper-0" : "bg-paper-0"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        <select
          data-testid="sort"
          value={sort}
          onChange={(e) => setSort(e.target.value as Sort)}
          className="border-2 border-surface-ink bg-paper-0 px-2 py-2 text-sm font-bold"
        >
          <option value="newest">Newest</option>
          <option value="volume">Volume</option>
          <option value="liquidity">Liquidity</option>
          <option value="ending">Ending soon</option>
        </select>
      </div>

      {error && (
        <div className="bread-card border-system-red p-4 text-system-red">
          <p className="font-bold">
            {IS_LOCAL
              ? "Could not reach the chain. Is anvil running and are the contracts deployed?"
              : `Could not load markets from ${CHAIN_LABEL}. The public RPC is unreachable or rate-limiting; retrying automatically.`}
          </p>
          <p className="mt-1 break-all text-caption">{String(error)}</p>
        </div>
      )}
      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <MarketCardSkeleton key={i} />
          ))}
        </div>
      )}
      {!isLoading && shown.length === 0 && (
        <div className="bread-card p-8 text-center">
          <p className="mb-3 font-bold">No markets found.</p>
          <Link to="/create">
            <Button variant="secondary">Open the first one</Button>
          </Link>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="market-grid">
        {shown.map((m) => (
          <MarketCard key={m.id} m={m} />
        ))}
      </div>
    </div>
  );
}
