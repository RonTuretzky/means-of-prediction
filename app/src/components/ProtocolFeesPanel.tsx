import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@breadcoop/ui";
import { abis } from "../contracts/gen";
import type { MarketData } from "../hooks/useMarkets";
import { publicClient, useWallet } from "../lib/wallet";
import { fmtAmount } from "../lib/format";
import { formatFeePercent } from "../lib/fees";
import { explain } from "./TradeWidget";

export function ProtocolFeesPanel({ m }: { m: MarketData }) {
  const wallet = useWallet();
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const { data: accrued, error: readError, isFetching, refetch } = useQuery({
    queryKey: ["protocol-fees", m.fpmm],
    enabled: m.protocolFee !== null && m.protocolFee > 0n,
    refetchInterval: 10_000,
    retry: 1,
    queryFn: () => publicClient.readContract({ address: m.fpmm, abi: abis.FPMM,
      functionName: "protocolFeesAccrued" }) as Promise<bigint>,
  });
  if (m.protocolFee === null || m.protocolFee === 0n || !m.feeRecipient) return null;

  const collect = async () => {
    if (inFlight.current || readError || isFetching || !accrued || !wallet.connected) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    setConfirmed(false);
    try {
      await wallet.write({ address: m.fpmm, abi: abis.FPMM, functionName: "withdrawProtocolFees" });
      setConfirmed(true);
      await refetch();
    } catch (error) {
      setError(explain(error));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <div className="bread-card p-4" data-testid="protocol-fees-panel">
      <h3 className="mb-2 font-breadDisplay text-lg font-bold uppercase">Platform revenue</h3>
      <p className="text-sm">{formatFeePercent(m.protocolFee)}% of gross trade value supports the platform, separate from LP fees.</p>
      <p className="my-2 text-sm">Available: <span data-testid="protocol-fees-accrued">
        {readError ? "Unavailable" : accrued === undefined ? "Loading…" : fmtAmount(accrued, m.collateral.decimals, { dollar: false })}
      </span> {m.collateral.symbol}</p>
      <p className="mb-2 break-all text-caption text-surface-grey-2">Fixed treasury: {m.feeRecipient}. Anyone can trigger payment; funds always go to this address.</p>
      {readError && (
        <div className="mb-2 text-caption text-system-red" role="alert" data-testid="protocol-fees-read-error">
          Could not load platform revenue. {explain(readError)}
          <button className="ml-2 underline" disabled={isFetching} onClick={() => void refetch()}>Retry</button>
        </div>
      )}
      {!wallet.connected ? (
        <Button size="sm" variant="light" data-testid="connect-protocol-fees"
          onClick={() => wallet.connect().catch((error) => setError(explain(error)))}>Connect wallet to send fees</Button>
      ) : (
        <Button size="sm" variant="light" data-testid="collect-protocol-fees" onClick={collect}
          isLoading={busy} disabled={!accrued || !!readError || busy || isFetching}>Send fees to treasury</Button>
      )}
      {confirmed && <p role="status" className="mt-2 text-caption text-system-green">Treasury withdrawal confirmed.</p>}
      {error && <p role="alert" data-testid="protocol-fees-error" className="mt-2 text-caption text-system-red">{error}</p>}
    </div>
  );
}
