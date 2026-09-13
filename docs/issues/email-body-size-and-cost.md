# Backlog: large DKIM email bodies exceed transaction size and gas budgets without a succinct proof

Priority: P1. Recorded 2026-09-10 against the body-parsing v1 working tree. These changes are not all published to the repository yet.

A valid newspaper email can contain a short, useful sentence inside a much larger HTML newsletter. Our direct RSA/DKIM path must authenticate the entire canonical body against the signed `bh=` hash before accepting a selected excerpt. Cropping the body and hashing only the useful sentence is not valid DKIM verification.

## Measured behavior

| Fixture / local test | Canonical body bytes | Settlement receipt gas | Result |
|---|---:|---:|---|
| NYT election newsletter, exact election-headline substring | 162,021 | 15,059,245 | Local Anvil lifecycle passed; full ABI transaction exceeds the common 128 KiB relay limit |
| NYT jobs alert, exact unemployment-rate substring | 79,351 | 8,685,448 | Local Anvil lifecycle passed; direct payload fits the common relay limit |
| Labelled synthetic body fixture, Sepolia | 102 | 4,784,485 | Public create → buy → body settlement → redeem → platform-fee withdrawal passed |

[Public synthetic settlement receipt](https://eth-sepolia.blockscout.com/tx/0xa5de08881d4365dfc6fbbdc78e2ed6edd752bc843faf7d12c48bd87b8d866211). Private mailbox bodies and local test artifacts are not attached to this issue. The real-email tests created separate explicit substring-rule markets; they did not settle original Polymarket contracts.

Gas depends on regex complexity, witness length, calldata, and chain gas schedule. These are receipt measurements for specific tests, not universal costs or a benchmark of the marginal SHA-256 precompile alone. Public and local fixture runs have different gas environments.

## Independent limits

1. **Relay size:** Geth's legacy txpool admits transactions up to `4 * 32 KiB = 128 KiB`. This is a client relay policy on the serialized transaction, not a universal EVM calldata consensus limit. ABI encoding, headers, RSA signature, excerpt, and transaction envelope consume space in addition to the body. A successful `eth_call` or Anvil transaction does not establish public relay acceptance. [Geth source](https://github.com/ethereum/go-ethereum/blob/master/core/txpool/legacypool/legacypool.go).
2. **Execution gas:** EIP-7825 caps a transaction's gas limit at 16,777,216 on activated chains, including our current Sepolia target. An email that fits transport can still exceed this cap. Splitting uploads does not split the final verifier/regex execution. [EIP-7825](https://eips.ethereum.org/EIPS/eip-7825).
3. **Application bounds:** v1 permits at most 196,608 canonical body bytes and a 4,096-byte encoded witness window. A window is QP-decoded and matched against the authenticated body source. HTML markup and entities remain source text; this is not browser-rendered text extraction.
4. **MIME support:** v1 supports single-part text/plain or text/html with UTF-8/ASCII. It rejects multipart, signed base64 transfer encoding, body-length-truncated (`l=`) signatures, and unsupported canonicalization/encoding. In the retained 131-email NYT corpus, 122 match this MIME profile and 9 are multipart. Profile compatibility does not imply affordable or rule-valid settlement.
5. **Predicate limits:** exact substring evidence does not itself implement numeric arithmetic, event identity, official-source rules, or negative-outcome settlement. Current email proof submission resolves YES; a defeat headline cannot directly resolve the corresponding original market NO. No proof system automatically fixes a badly specified rule.

## Pagination mitigation under implementation

`EmailBodyStore` stores up to 24,000 bytes per immutable data contract (a leading STOP byte prevents executing the stored text), with a maximum of 9 pages / 196,608 body bytes. Anyone can upload pages in separate transactions; the final transaction supplies ordered addresses, the store assembles the bytes, and the existing verifier checks RSA plus the signed full-body hash before matching the excerpt. Content hashes deduplicate pages and allow interrupted uploads to resume. Reordered, omitted, or altered bytes cannot pass `bh=` verification.

The five initial Foundry pagination tests pass, including tampering, unknown pages, bounds, deduplication, and settlement/redemption. All 170 contract tests and all 10 browser flows now pass, including a large paginated upload, settlement and redemption. A 147,431-byte synthetic public fixture also passed the full paginated lifecycle on Sepolia.

This reduces the final transaction's calldata size. It **adds** deployment/storage transactions and gas. Runtime code deposit alone is roughly 200 gas/byte: a 162,021-byte body costs about 32.4M gas in data-code deposit across pages, before upload calldata, creation overhead, and final settlement. This is a deposit-only cost model. The now-completed local 162,021-byte test measured **35,997,721 upload gas + 12,803,112 final settlement gas = 48,800,833 total**; final calldata was **3,236 bytes**, down from **164,964 direct-call bytes**. The public 147,431-byte synthetic test measured **32,821,063 upload gas + 4,663,797 final gas = 37,484,860 total**, with **1,828 final-call bytes**. [Public paginated settlement](https://eth-sepolia.blockscout.com/tx/0x5470d5823a8eeb49b5dd91f0ac1d3192b57964af192b6c5708d40ba794fe4e83). The nine public direct/upload/final envelopes were reconstructed and matched to their mined hashes; the largest upload was 24,185 serialized bytes and the final paginated settlement was 1,945 serialized bytes. All were within the relay and transaction gas bounds. These totals exclude market/core creation, trading and redemption; private data remained local. All body bytes become public and persist. Upload cost may be shared across multiple markets using the same email.

## Alternatives and tradeoffs

- **Pagination:** preserve direct onchain RSA/full-body verification; solve transport, not total cost or arbitrary execution limits.
- **Incremental SHA-256:** possible without ZK, but requires an audited continuation-state design, block alignment, final padding/length checks, and binding to the signed `bh=`. Ethereum's SHA precompile does not expose resumable compression state. A Merkle root invented by the submitter is not authenticated by the publisher's DKIM signature.
- **ZK / succinct validity proof:** prove RSA/header binding, canonical-body hash opening, parsing, and the exact predicate; expose domain/key, rules, timestamp, outcome and replay commitments as public inputs. Potentially remove full-body calldata and expensive repeated execution. Measure proof generation and verification before selecting a system. A regex-only proof with no authenticated email binding is insufficient.
- **GasKiller:** evaluate compact operator-attested computation separately; ingress, availability, and trust assumptions are tracked in [the companion issue](https://github.com/RonTuretzky/means-of-prediction/issues/2).

## Acceptance criteria

- [x] Browser and bot choose direct or paginated transport based on actual ABI size with envelope headroom; explain page count, public data, and cost before submission.
- [ ] Test public synthetic bodies above 128 KiB, boundary sizes, interrupted/resumed uploads, wrong order, changed body, invalid RSA, replay, and final gas cap.
- [ ] Record per-upload gas, final gas, total gas, transaction sizes, and amortization across several markets; never present pagination as inherently cheaper.
- [x] Reject unsupported MIME/patterns with actionable errors; publish the versioned byte-level parsing rules.
- [ ] Benchmark direct, paginated, and candidate succinct/attested paths on the same privacy-safe corpus and chain configuration.
- [ ] Preserve original source, event, deadline and outcome requirements in any new settlement mode.
