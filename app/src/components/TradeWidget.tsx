import { useEffect, useMemo, useState } from "react";
import { Button } from "@breadcoop/ui";
import { formatUnits, maxUint256 } from "viem";
import { abis } from "../contracts/gen";
import { CT, Resolution, useBalances, type MarketData } from "../hooks/useMarkets";
import { fmtAmount, fmtCents, parseAmount } from "../lib/format";
import { publicClient, useWallet } from "../lib/wallet";
import { useToast } from "./Toast";

const SLIPPAGE_BPS = 100n; // 1% tolerance vs quoted amount

type Side = 0 | 1; // 0 = YES, 1 = NO
type Tab = "buy" | "sell";

export function TradeWidget({ m }: { m: MarketData }) {
  const wallet = useWallet();
  const toast = useToast();
  const { data: bal } = useBalances(wallet.address, m);
  const [tab, setTab] = useState<Tab>("buy");
  const [side, setSide] = useState<Side>(0);
  const [amount, setAmount] = useState(""); // buy: dollars in; sell: shares out
  const [quote, setQuote] = useState<bigint | null>(null); // buy: shares; sell: dollars received
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const dec = m.collateral.decimals;
  const units = parseAmount(amount, dec);
  const price = side === 0 ? m.priceYes : m.priceNo;
  const tradingOpen = m.resolution === Resolution.Unresolved;

  // Quote: calcBuyAmount for buys; for sells, binary-search the collateral return
  // for the entered share count (the contract prices exact-collateral-out).
  useEffect(() => {
    let stale = false;
    setQuote(null);
    setError(null);
    if (!units || units === 0n) return;
    (async () => {
      try {
        if (tab === "buy") {
          const shares = (await publicClient.readContract({
            address: m.fpmm,
            abi: abis.FPMM,
            functionName: "calcBuyAmount",
            args: [units, BigInt(side)],
          })) as bigint;
          if (!stale) setQuote(shares);
        } else {
          let lo = 0n;
          let hi = units; // shares always fetch less collateral than face value
          for (let i = 0; i < 40 && lo < hi; i++) {
            const mid = (lo + hi + 1n) / 2n;
            try {
              const needed = (await publicClient.readContract({
                address: m.fpmm,
                abi: abis.FPMM,
                functionName: "calcSellAmount",
                args: [mid, BigInt(side)],
              })) as bigint;
              if (needed <= units) lo = mid;
              else hi = mid - 1n;
            } catch {
              hi = mid - 1n; // return too large for pool liquidity
            }
          }
          if (!stale) setQuote(lo > 0n ? lo : null);
        }
      } catch (e) {
        if (!stale) setError(explain(e));
      }
    })();
    return () => {
      stale = true;
    };
  }, [amount, tab, side, m.fpmm, m.priceYes, m.priceNo]);

  const notEnough =
    tab === "buy"
      ? bal !== undefined && units !== null && units > bal.cash
      : bal !== undefined && units !== null && units > (side === 0 ? bal.yes : bal.no);

  const submit = async () => {
    if (!units || !quote) return;
    setBusy("submitting");
    setError(null);
    try {
      if (tab === "buy") {
        const allowance = (await publicClient.readContract({
          address: m.collateral.address,
          abi: abis.TestUSDC,
          functionName: "allowance",
          args: [wallet.address, m.fpmm],
        })) as bigint;
        if (allowance < units) {
          await wallet.write({
            address: m.collateral.address,
            abi: abis.TestUSDC,
            functionName: "approve",
            args: [m.fpmm, maxUint256],
          });
        }
        const minShares = quote - (quote * SLIPPAGE_BPS) / 10000n;
        await wallet.write({
          address: m.fpmm,
          abi: abis.FPMM,
          functionName: "buy",
          args: [units, BigInt(side), minShares],
        });
        toast.push({
          kind: "success",
          title: `Bought ${fmtAmount(quote, dec, { dollar: false, dp: 0 })} ${side === 0 ? "Yes" : "No"}`,
          detail: `for ${fmtAmount(units, dec)} · to win ${fmtAmount(quote, dec)}`,
        });
      } else {
        const approved = (await publicClient.readContract({
          address: CT,
          abi: abis.ConditionalTokens,
          functionName: "isApprovedForAll",
          args: [wallet.address, m.fpmm],
        })) as boolean;
        if (!approved) {
          await wallet.write({
            address: CT,
            abi: abis.ConditionalTokens,
            functionName: "setApprovalForAll",
            args: [m.fpmm, true],
          });
        }
        // `quote` is the max collateral for exactly `units` shares on the current
        // snapshot. Request 1% less so a pool move between quote and mining still fits
        // within the user's share balance (maxShares can't exceed what they hold).
        const minReturn = quote - (quote * SLIPPAGE_BPS) / 10000n;
        await wallet.write({
          address: m.fpmm,
          abi: abis.FPMM,
          functionName: "sell",
          args: [minReturn, BigInt(side), units],
        });
        toast.push({
          kind: "success",
          title: `Sold ${fmtAmount(units, dec, { dollar: false, dp: 0 })} ${side === 0 ? "Yes" : "No"}`,
          detail: `received ~${fmtAmount(minReturn, dec)}`,
        });
      }
      setAmount("");
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(null);
    }
  };

  const quickAdd = (v: number) => {
    const cur = parseFloat(amount || "0") || 0;
    setAmount(String(cur + v));
  };

  const toWin = tab === "buy" && quote !== null ? quote : null;

  if (!tradingOpen) {
    return (
      <div className="bread-card p-4">
        <h3 className="font-breadDisplay text-lg font-bold">Trading closed</h3>
        <p className="text-sm text-surface-grey-2">
          This market has resolved {m.resolution === Resolution.Yes ? "YES" : "NO"}. Redeem your winning shares
          below.
        </p>
      </div>
    );
  }

  if (m.lpSupply === 0n) {
    return (
      <div className="bread-card p-4" data-testid="trade-widget">
        <h3 className="font-breadDisplay text-lg font-bold">No liquidity yet</h3>
        <p className="text-sm text-surface-grey-2">
          This market exists onchain but its pool is empty, so trades can't be priced yet. Be the first LP —
          add funding in the Liquidity panel (you set the opening odds) and trading opens instantly.
        </p>
      </div>
    );
  }

  return (
    <div className="bread-card p-4" data-testid="trade-widget">
      <div className="mb-3 flex border-2 border-surface-ink">
        {(["buy", "sell"] as Tab[]).map((t) => (
          <button
            key={t}
            data-testid={`tab-${t}`}
            onClick={() => {
              setTab(t);
              setAmount("");
            }}
            className={`flex-1 px-3 py-2 font-breadDisplay font-bold uppercase ${
              tab === t ? "bg-surface-ink text-paper-0" : "bg-paper-0 text-surface-ink"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="mb-3 flex gap-2">
        <button
          data-testid="side-yes"
          onClick={() => setSide(0)}
          className={`flex-1 border-2 px-3 py-2 font-bold ${
            side === 0
              ? "border-system-green bg-system-green text-white"
              : "border-surface-ink bg-paper-0 text-surface-ink"
          }`}
        >
          Yes {fmtCents(m.priceYes)}
        </button>
        <button
          data-testid="side-no"
          onClick={() => setSide(1)}
          className={`flex-1 border-2 px-3 py-2 font-bold ${
            side === 1 ? "border-system-red bg-system-red text-white" : "border-surface-ink bg-paper-0 text-surface-ink"
          }`}
        >
          No {fmtCents(m.priceNo)}
        </button>
      </div>

      <label className="text-caption font-bold uppercase text-surface-grey-2">
        {tab === "buy" ? `Amount (${m.collateral.symbol})` : "Shares to sell"}
      </label>
      <input
        data-testid="amount-input"
        inputMode="decimal"
        placeholder="0"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        className="mb-2 w-full border-2 border-surface-ink bg-paper-0 px-3 py-2 text-xl font-bold outline-none focus:border-core-orange"
      />
      <div className="mb-3 flex gap-1">
        {[1, 20, 100].map((v) => (
          <button
            key={v}
            onClick={() => quickAdd(v)}
            className="border border-surface-ink px-2 py-0.5 text-caption font-bold hover:bg-paper-1"
          >
            +${v}
          </button>
        ))}
        <button
          onClick={() => {
            if (!bal) return;
            const max = tab === "buy" ? bal.cash : side === 0 ? bal.yes : bal.no;
            // Exact balance — rounding to 2dp could round UP past the balance and trip
            // the "not enough" guard, blocking a genuine max trade.
            setAmount(formatUnits(max, dec));
          }}
          className="border border-surface-ink px-2 py-0.5 text-caption font-bold hover:bg-paper-1"
        >
          Max
        </button>
      </div>

      <div className="mb-3 space-y-1 text-sm">
        {tab === "buy" ? (
          <>
            <div className="flex justify-between">
              <span className="text-surface-grey-2">Shares</span>
              <span data-testid="quote-shares">{quote !== null ? fmtAmount(quote, dec, { dollar: false }) : "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-surface-grey-2">Avg price</span>
              <span>
                {quote !== null && quote > 0n && units
                  ? fmtCents((units * 10n ** 18n) / quote)
                  : fmtCents(price)}
              </span>
            </div>
            <div className="flex justify-between text-base font-black text-system-green">
              <span>To win</span>
              <span data-testid="to-win">{toWin !== null ? fmtAmount(toWin, dec) : "$0.00"}</span>
            </div>
          </>
        ) : (
          <div className="flex justify-between text-base font-black">
            <span>You'll receive</span>
            <span data-testid="youll-receive">{quote !== null ? fmtAmount(quote, dec) : "$0.00"}</span>
          </div>
        )}
        <div className="flex justify-between text-caption text-surface-grey-2">
          <span data-testid="trade-fees">Fees included: {Number(m.fee) / 1e16}% to liquidity providers + {Number(m.protocolFee) / 1e16}% platform ({Number(m.fee + m.protocolFee) / 1e16}% total). Max slippage 1%.</span>
        </div>
      </div>

      {error && (
        <div className="mb-2 border-2 border-system-red bg-red-0 px-2 py-1 text-caption text-system-red">{error}</div>
      )}
      {notEnough && (
        <div className="mb-2 text-caption font-bold text-system-red">
          {tab === "buy" ? "Not enough funds" : "Not enough shares"}
        </div>
      )}

      <Button
        data-testid="trade-submit"
        className="w-full"
        variant={side === 0 ? "positive" : "destructive"}
        disabled={!units || !quote || !!busy || notEnough}
        isLoading={!!busy}
        showChildrenWhenLoading
        onClick={submit}
      >
        {busy
          ? `Placing ${tab} order`
          : !units
            ? "Must specify amount"
            : `${tab === "buy" ? "Buy" : "Sell"} ${side === 0 ? "Yes" : "No"}`}
      </Button>
      <p className="mt-2 text-center text-caption text-surface-grey-2">
        Settlement uses public DKIM signatures verified onchain. Winning shares redeem without an additional platform fee.
      </p>
    </div>
  );
}

export function explain(e: unknown): string {
  const msg = e instanceof Error ? e.message : String(e);
  const m = msg.match(/reverted with the following reason:\s*\n?\s*(.+?)(\n|$)/);
  if (m) return m[1];
  const m2 = msg.match(/reason:\s*(.+?)(\n|$)/);
  if (m2) return m2[1];
  return msg.split("\n")[0].slice(0, 200);
}
