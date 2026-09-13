# Authenticated email bodies and paginated submission

Updated 2026-09-10. The new Sepolia deployment supports body-source substring rules with RSA/DKIM verification and optional paginated body uploads. ZK is not required. Original Gnosis clones are immutable and have not been migrated.

## What the contract authenticates

`EmailProof` adds `canonicalBody`, `bodyOffset`, and `bodyLength` to the existing header/signature fields. The browser and bot preserve the raw email octets, canonicalize the body offchain according to the signed DKIM `c=`, and supply the complete canonical bytes. RSA-SHA256 PKCS#1 v1.5 authenticates the signed header and its `bh=` commitment; the contract computes SHA-256 over the supplied complete body and requires equality. It decodes the selected bounded byte window itself and requires the decoded bytes to equal `bodyExcerpt` before matching the configured regex.

The verifier also binds exact signed Subject, parsed From mailbox, Date/timestamp, signing domain, registered key hash and signature-derived nullifier. The registry trusts its fixed registrar to authenticate DNS keys. It is not a DNSSEC proof or historical-key validity oracle.

Subject-only proofs leave all body fields empty. Existing deployed subject-only markets use a legacy tuple ABI selected by deployment metadata; new deployments advertise `bodyParsingVersion: 1`. Judged markets remain the separate existing Subject-based GasKiller path. The fresh Sepolia factory has `judge == address(0)`.

## Body-source profile v1

- Maximum canonical body: **196,608 bytes (192 KiB)**. Maximum encoded window: **4,096 bytes**. Maximum signed header: 32,768 bytes.
- Require a unique signed `Content-Type` with single-part `text/plain` or `text/html`; declared charset, when present, must be UTF-8 or US-ASCII. This is source-byte matching, not browser rendering or a complete MIME parser.
- If a unique signed `Content-Transfer-Encoding` exists, accept quoted-printable or identity 7bit/8bit. Reject signed base64 and unsupported encodings.
- If the encoding header is not signed, **v1 fixes the interpretation to quoted-printable** and ignores the unsigned header. NYT commonly signs Content-Type but not CTE. No unsigned field selects the interpretation of signed bytes.
- Quoted-printable decoding handles hexadecimal escapes and soft CRLF breaks. Reject invalid/dangling escapes or windows beginning inside an escape. HTML tags, entities, links, comments and hidden source remain source text. A match does not establish that a browser displayed the text.
- Accept explicit `c=relaxed/relaxed` or `c=relaxed/simple`. Reject DKIM `l=` truncation, duplicate/ambiguous body-hash or canonicalization tags, and malformed SHA-256 base64.
- Body windows are existential **substring** witnesses. Unescaped `^`/`$` anchors outside character classes are disallowed for body-only rules; the Body branch of SubjectOrBody refuses them. Subject matching retains its normal anchors.
- The browser selects a tight match window to limit decoding/matcher work. Regex execution is byte-oriented and costs depend on the pattern and window. The app's normal text importer refuses invalid UTF-8 witness decoding.

All 131 retained NYT emails have canonical body hashes matching their signed `bh=`. Of these, 122 fit this MIME profile; nine are multipart. Neither fact proves that all 122 fit gas budgets or qualify under any particular market's rules.

## Pagination: transport, not cheaper verification

`EmailBodyStore.storeChunk(bytes)` deploys an immutable data-only contract containing one leading STOP byte and up to **24,000 bytes** of body. `chunkForHash(keccak256(chunk))` permits deduplication and resuming after interruption. Uploaders need no role. The store accepts at most nine pointers and enforces the same 196,608-byte total bound.

For finalization, `submitWithChunks(market, sourceIndex, compactProof, pointers)` requires an empty `compactProof.canonicalBody`, concatenates the ordered stored bytes, and calls the existing market with the reconstructed proof. `checkWithChunks` provides the same read-only preflight. Unknown pointers, reordered/altered content and body-hash mismatches fail. Stored pages grant no authentication authority. The market records the store as the forwarding submitter; the original transaction sender remains visible in the transaction.

The browser and bot compute the direct ABI size with 200 bytes of envelope headroom. Above common 128 KiB relay policy, a deployment with `emailBodyStore` uses page uploads followed by the compact final transaction. The UI shows the upload count and public-data/cost implications. Confirmed pages are reused on retry. The bot's dry run reports a planned paginated submission; it does not claim the final call has been simulated before pages exist.

Geth's 128 KiB txpool limit is a client relay policy, not a universal EVM calldata cap. EIP-7825 separately caps transaction gas at 16,777,216 on activated Ethereum chains, including current Sepolia. Pagination does not split final RSA/hash/parser/regex execution or raise the app's 192 KiB bound. Each page and final transaction must be affordable and executable separately. All uploaded bytes are permanently public.

## Measured end-to-end results

These are transaction receipt measurements from specific tests; local and public-chain gas schedules differ. Private NYT bodies stayed on a private local Anvil chain. Public tests use synthetic content signed under the explicitly non-newspaper domain `body-fixture.invalid`.

| Test | Full body | Direct calldata | Page upload gas | Final settlement gas | Uploads + final |
|---|---:|---:|---:|---:|---:|
| Real NYT exact election headline, local direct | 162,021 B | 164,964 B | — | 15,059,245 | 15,059,245; too large for common public relay |
| Same real NYT headline, local paginated | 162,021 B | final: 3,236 B | 35,997,721 (7 pages) | 12,803,112 | **48,800,833** |
| Real NYT exact unemployment sentence, local direct | 79,351 B | below relay limit | — | 8,685,448 | 8,685,448 |
| Public synthetic fixture, Sepolia direct | 102 B | below relay limit | — | 4,784,485 | 4,784,485 |
| Public synthetic large fixture, Sepolia paginated | 147,431 B | original: 148,964 B; final: 1,828 B | 32,821,063 (7 pages) | 4,663,797 | **37,484,860** |

Totals cover body uploads and settlement, not one-time core deployment, market creation, trading or redemption. Reusing the same immutable pages across markets can amortize upload cost. Pagination solves size, but the first real-email submission above costs more than three times its local direct counterpart.

The nine public direct/upload/final transaction envelopes were reconstructed and their hashes matched to mined transactions: the largest upload was 24,185 serialized bytes, and the paginated final transaction was 1,945 serialized bytes. All gas limits were below 16,777,216.

Each complete lifecycle created an explicit body-substring market, funded liquidity, bought YES shares, rejected forged excerpts/altered bodies, accepted valid evidence, redeemed a winner, withdrew the 1% platform fee, and rejected replay. Paginated tests also reject reordered pages. The direct NYT tests are retrospective explicit rules, not executions of original Polymarket oracle rules.

## Sepolia deployment and public receipts

Authoritative addresses: [`contracts/deployments/sepolia.json`](../contracts/deployments/sepolia.json).

- Factory: [`0xdbe9c7f2333a0705eefcac15c58d70859b5b1e2f`](https://eth-sepolia.blockscout.com/address/0xdbe9c7f2333a0705eefcac15c58d70859b5b1e2f)
- DKIM verifier: [`0x9e66b9d05d595b47f8dad91161cfa1749849d1d6`](https://eth-sepolia.blockscout.com/address/0x9e66b9d05d595b47f8dad91161cfa1749849d1d6)
- Body store: [`0xb15d8bf694aab06731d7debb17adac22b10ac3b1`](https://eth-sepolia.blockscout.com/address/0xb15d8bf694aab06731d7debb17adac22b10ac3b1)
- [Direct synthetic settlement](https://eth-sepolia.blockscout.com/tx/0xa5de08881d4365dfc6fbbdc78e2ed6edd752bc843faf7d12c48bd87b8d866211)
- [Paginated synthetic settlement](https://eth-sepolia.blockscout.com/tx/0x5470d5823a8eeb49b5dd91f0ac1d3192b57964af192b6c5708d40ba794fe4e83)
- [Paginated-case winning redemption](https://eth-sepolia.blockscout.com/tx/0xf002f3c4942e97d3cd05e2fb4fe200737f39d94636382108435dc86766efd8ab)
- [Paginated-case platform fee withdrawal](https://eth-sepolia.blockscout.com/tx/0x915d6f4f8fc2c9bea9d4a7d3a05bb71ba831addd1d8e378bfd1fcd748bc89ad5)

Runtime bytecode was compared to compiled artifacts (linked library addresses filled; constructor immutable slots masked), and factory wiring/version were read back. Four observed NYT domain/selector keys were obtained from current DNS and registered. The public fixture key was registered only under `body-fixture.invalid`, never under a newspaper domain. Sepolia uses test collateral and the existing test deployer as fee recipient.

## Validation and running it

- **170 Foundry tests** passed, including 13 body-parser and five body-store tests plus the existing RSA, market, fee and LLM suites.
- **10 Playwright browser flows** passed, including a >128 KiB body upload through the UI, tamper rejection, seven-page settlement, and redemption. An upload/key-loading race found during this run was fixed by awaiting the registry query.
- **7 Node body tests** passed. All ten featured slideshow regexes passed both real-email RSA/full-body verification and the Solidity matcher on local Anvil.

From repository root: `forge test --root contracts`. From `app/`: `npm run test:body`, `npm run e2e`, and `DEPLOYMENT=sepolia npm run build`.

`app/scripts/body-e2e.mjs` is a resumable deployment/test runner. Default mode uses local Anvil on port 8559 (chain ID 31337); `--sepolia` checks chain ID 11155111 and loads the existing private deployment configuration in-process. `--large-fixture` adds paginated synthetic testing. `--real-email <private path>` is local-only and is explicitly refused in public mode. Private receipt/evidence reports are outside the repository. Local, Sepolia and Gnosis Foundry deploy scripts now include the store and metadata for future fresh deployments; this work broadcast only to Sepolia.

## Remaining work

- [Issue #1: body size/cost, broader MIME and proof alternatives](https://github.com/RonTuretzky/means-of-prediction/issues/1).
- [Issue #2: proposed GasKiller adapter](https://github.com/RonTuretzky/means-of-prediction/issues/2), with `@tbsoc` and `@nomoregas` tagged. Its service currently also limits combined input/output to 128 KiB. A compact operator-attested body predicate needs ingress changes, explicit receipt binding, and a documented trust/availability model.
- Full ZK validity proofs could reduce data/computation while adding proving cost and proof-system dependencies. A regex-only proof without DKIM/body/rule binding is insufficient. No ZK replacement has been benchmarked here.
- Numeric scores, tournament/event identity, official-source acceptance and direct NO evidence require explicit rule logic. Current email proof submission resolves YES; none of the original Polymarket markets was settled by this audit. The 149 findings remain factual matches, not 149 deployable exact-rule settlement proofs.
- Gnosis migration, production treasury choices, and publishing the built app await the existing shared-worktree release coordination. No commits, pushes, or Pages publication were made.

Primary protocol references: [DKIM RFC 6376](https://www.rfc-editor.org/rfc/rfc6376), [MIME transfer encoding RFC 2045](https://www.rfc-editor.org/rfc/rfc2045), [Geth txpool policy](https://github.com/ethereum/go-ethereum/blob/master/core/txpool/legacypool/legacypool.go), [EIP-7825](https://eips.ethereum.org/EIPS/eip-7825).
