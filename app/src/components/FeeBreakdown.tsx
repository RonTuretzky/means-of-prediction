import { formatFeePercent } from "../lib/fees";

export function FeeBreakdown({ lpFee, protocolFee, totalFee, legacy = false }: {
  lpFee: bigint; protocolFee: bigint; totalFee: bigint; legacy?: boolean;
}) {
  return (
    <div data-testid="trade-fees" className="space-y-1 text-caption text-surface-grey-2">
      <div className="flex justify-between gap-2"><span>Liquidity provider fee</span><span>{formatFeePercent(lpFee)}%</span></div>
      <div className="flex justify-between gap-2"><span>Platform fee</span><span>{formatFeePercent(protocolFee)}%</span></div>
      <div className="flex justify-between gap-2 font-bold text-surface-ink"><span>Total trading fee (included)</span><span>{formatFeePercent(totalFee)}%</span></div>
      {legacy && <p>Legacy pool: no platform fee.</p>}
      <p>Rates apply to gross trade value. Sell quotes include the fee gross-up. Max slippage 1%.</p>
    </div>
  );
}
