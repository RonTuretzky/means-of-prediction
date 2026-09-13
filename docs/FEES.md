# Platform fees

New deployments default to a **1% platform fee on each buy and sell**, in addition to the market creator's LP fee (default 2%). Existing deployed pools have no platform fee and are displayed as such.

`MarketFactory` fixes `protocolFee` and `feeRecipient` at deployment. Each new pool copies those settings; a creator cannot disable the platform charge. Both values have no setter. Deploy scripts accept `PROTOCOL_FEE` in 1e18 scale (`10000000000000000` = 1%) and `FEE_RECIPIENT` (defaults to the broadcasting deployer). Set an appropriate treasury address before a real deployment. Platform rates above 5%, missing recipients for nonzero rates and combined fees of 100% or more are rejected.

The FPMM's existing `fee()` remains the LP rate; `totalFee()` is LP plus platform. Quotes and trade execution use that total. For a $100 buy with 2% LP + 1% platform, $97 is split into outcome tokens, $2 accrues to LPs and $1 accrues to the treasury. A sell for exactly $97 net merges $100 of complete sets with the same split. Integer rounding favors the pool; with no LP fee, rounding dust belongs to the platform.

`protocolFeesAccrued()` is separate collateral accounting. Anyone can call `withdrawProtocolFees()` but the payment always goes to the pool's fixed `feeRecipient`. LP withdrawals cannot collect platform revenue. Withdrawal clears the credit before transferring, so repeated calls cannot double-collect. Liquidity funding/withdrawal and winning-share redemption have no additional platform charge.

No new fees can be added to existing EIP-1167 clones. New fee-enabled markets require a new deployment. This refactor does not migrate live positions or change the existing pools' economics.

Tests in `contracts/test/ProtocolFees.t.sol` cover buy/sell quotes, separation from LP entitlements, treasury-only payout, repeated withdrawal, zero LP fees, configuration bounds and fuzzed collateral conservation.
