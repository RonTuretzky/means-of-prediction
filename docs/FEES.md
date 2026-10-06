# Operator fees

New deployments default to a **2.2% operator/platform fee**, additional to the
creator-selected liquidity-provider (LP) fee, whose app default remains **2%**.
The default combined trading fee is therefore **4.2% of the gross collateral
amount**. This is a fixed-rate AMM fee, not Polymarket's probability-dependent
order-book fee model.

## Accounting and rounding

The existing `FPMM.fee()` remains the LP rate. `protocolFee()` is separate and
`totalFee()` is their sum. Both buy/sell quotes and trade execution use the same
combined rate. On a 100-unit buy at the defaults, 2 units accrue to LPs, 2.20 to
the operator, and 95.80 enter outcome-token pricing before price impact. A sell
for exactly 95.80 units net merges 100 units of complete sets with the same split.
Gas and slippage are separate from these fees.

Amounts are calculated in the collateral token's smallest units, for both
6-decimal and 18-decimal tokens. Buy total fees round down. Exact-net-output
sells round gross collateral up. The operator's portion rounds down from the
same gross amount, with the remaining fee rounding dust allocated to LPs. If
the LP fee is zero, all fee rounding dust goes to the operator. Consequently
tiny trades can differ from a simple decimal percentage display.
As with the existing FPMM, collateral must follow ordinary ERC-20 transfer
semantics; fee-on-transfer and rebasing tokens are not supported by this accounting.

`protocolFeesAccrued()` tracks operator collateral separately from LP fee
entitlements. Anyone may call `withdrawProtocolFees()`, but funds always go to
the pool's fixed `feeRecipient()`. No caller-selected destination is accepted.
The credit is cleared before transfer; a failed transfer reverts the credit
change. LP withdrawals cannot claim this operator balance. Funding, removing
liquidity, and redeeming winning shares have no additional operator charge.
LP mint/burn/transfer corrections retain full accumulator precision until the
final entitlement division, so repeated tiny share movements cannot fabricate
claims against the operator balance.

## Configuration and existing deployments

`MarketFactory` fixes `protocolFee` and `feeRecipient` in its constructor. New
FPMM clones copy those settings once during initialization. Neither has a setter,
and market creators cannot waive the operator fee. Factory operator rates above
5%, a zero recipient for a nonzero rate, and combined rates of 100% or more are
rejected.

Deployment scripts default `PROTOCOL_FEE` to `22000000000000000` (220 basis
points, 1e18-scaled). Real-network scripts require an explicitly supplied
`FEE_RECIPIENT` treasury address; they never default to the deployer's address.
The local development script uses a separate fixture treasury only on chain
31337. A real deployment requires reviewing the treasury and rate first.

Existing deployed EIP-1167 pools cannot be upgraded by this change. They keep
their original economics and positions. Fee-enabled markets require a new
factory/implementation deployment and updated app deployment addresses. This
PR does not perform that deployment, migrate funds, or change live addresses.
The frontend reads fees from contracts rather than assuming every existing
market has the new default rate.

## Publication safety

The workflow calls only the pinned, reviewed Etherform build/test workflow,
with no deployment job in its graph and no deployer credentials passed to it.
Publishing this branch or opening its PR must not send onchain transactions.
GitHub Pages remains restricted to main-branch pushes or manual dispatch, and
the existing settlement schedule is unchanged. No workflow is dispatched by
this change.

## Verification

Run `cd contracts && forge test` for full contract regressions, including the
fee-specific 6-/18-decimal suites in `test/ProtocolFees.t.sol`. Run
`cd app && pnpm test:fees && pnpm build` for fee parsing/compatibility tests and
the production build. `pnpm e2e` runs browser flows against an isolated local
Anvil chain; it must not be pointed at a public network.
Its Forge script runs with `--offline` after compilation, disabling optional
explorer metadata and selector lookups; no public contract verification is run.

CI checks formatting for the changed contract files. Existing formatting drift
elsewhere is intentionally left out of this fee-only change.
