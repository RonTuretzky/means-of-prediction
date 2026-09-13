# Vendored Gas Killer Solidity SDK (BLS scheme)

Verbatim copies of `gas-killer/solidity-sdk` `src/` files at the commit recorded in
`VENDORED_COMMIT` (AGPL-3.0-only, see LICENSE), plus a MINIMAL mirror of the
`eigenlayer-middleware` `IBLSSignatureChecker` types the SDK's ABI depends on
(`lib/eigenlayer-middleware/`, pinned upstream at BreadchainCoop/eigenlayer-middleware
fd26169c). Only the structs/functions `GasKillerSDK.verifyAndUpdate` touches are
mirrored — struct layouts are byte-identical so the settlement ABI matches the live
router's payloads. Vendored (like forge-std) rather than a submodule so the repo builds
without the full middleware tree.
