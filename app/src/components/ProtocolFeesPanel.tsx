import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@breadcoop/ui";
import { abis } from "../contracts/gen";
import type { MarketData } from "../hooks/useMarkets";
import { publicClient, useWallet } from "../lib/wallet";
import { fmtAmount } from "../lib/format";
import { explain } from "./TradeWidget";

export function ProtocolFeesPanel({ m }: { m: MarketData }) {
  const wallet = useWallet();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data: accrued, refetch } = useQuery({
    queryKey: ["protocol-fees", m.fpmm], enabled: m.protocolFee > 0n, refetchInterval: 10_000,
    queryFn: async () => await publicClient.readContract({ address: m.fpmm, abi: abis.FPMM,
      functionName: "protocolFeesAccrued" }) as bigint,
  });
  if (!m.protocolFee) return null;
  const collect = async () => {
    setBusy(true); setError(null);
    try {
      await wallet.write({ address: m.fpmm, abi: abis.FPMM, functionName: "withdrawProtocolFees" });
      await refetch();
    } catch(e) { setError(explain(e)); }
    finally { setBusy(false); }
  };
  return <div className="bread-card p-4" data-testid="protocol-fees-panel">
    <h3 className="mb-2 font-breadDisplay text-lg font-bold uppercase">Platform revenue</h3>
    <p className="text-sm">{Number(m.protocolFee) / 1e16}% of each trade supports the platform.</p>
    <p className="my-2 text-sm">Available: <span data-testid="protocol-fees-accrued">{accrued === undefined ? "…" : fmtAmount(accrued, m.collateral.decimals)}</span> {m.collateral.symbol}</p>
    <p className="mb-2 break-all text-caption text-surface-grey-2">Treasury: {m.feeRecipient}. Anyone can trigger payment; funds always go to this address.</p>
    <Button size="sm" variant="light" data-testid="collect-protocol-fees" onClick={collect} isLoading={busy} disabled={!accrued || busy}>Send fees to treasury</Button>
    {error && <p className="mt-2 text-caption text-system-red">{error}</p>}
  </div>;
}
