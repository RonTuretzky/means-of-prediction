# Google Alerts frontend and rule generation

Updated October 26, 2026.

## Product surfaces

- `/`: the rules → alerts → authentication → judgment → settlement product story.
- `/demo/peace-2026`: resolved-market layout for the audited four-report historical
  Nobel replay. Overview, Evidence, Rules and Verification tabs expose the result
  and its limits. The transaction is on local chain 31337. Original signatures
  were valid at the replay clock and have expired; source policy was selected
  after receipt. The page does not claim pre-close evidence, public settlement,
  trading volume, market odds or a payout.
- `/create/ai`: DeepSeek drafts YES, NO and abstention conditions, source proposals,
  event/timing requirements, Google Alerts queries with explicit jobs, and judge
  instructions. The draft is editable. Reviewed plans are stored in this browser
  and can be exported with a deterministic SHA-256 rules commitment and provider
  receipt. Alert links open the Google Alerts UI; the user must save each alert.
- `/demos`: the independent public Sepolia computation receipt. Its 32 QKV outputs
  are not the full judge or a market settlement.
- `/markets`, `/market/:id`, `/create`, `/portfolio`: existing on-chain interface.

## Live deployment

Frontend: `https://ronturetzky.github.io/means-of-prediction/` via the existing Pages
workflow. API: `https://means-of-prediction-rule-generator.ronturetzky.workers.dev`.
The build's `VITE_RULE_API_URL` points to that endpoint. Only this public address
is bundled; DeepSeek credentials and operator access codes are server secrets.

Generation requires a private demo operator access code. It is separate from the
provider key and retained only in page memory, not browser storage or exports.
The API uses `deepseek-flash`, JSON output, strict structural validation, exact
question/deadline preservation, bounded requests, timeout and rate limiting.
See `services/rule-generator/README.md` for commands and secret configuration.

Generated drafts still need semantic review: API validation checks structure, not
factual completeness or fair interpretation. Queries and `after:` filters are
discovery tools. Google authenticates email bytes; publisher truth, event timing,
source admissibility and independence remain separate requirements. No new
on-chain submission, automatic alert creation or monitor enrollment occurs when
the user saves a plan. Connecting those steps prospectively remains future work.

## Validation and maintenance

Frontend: `pnpm test:compute-demos`, `pnpm test:rule-studio`, `pnpm build` in `app`.
API: `npm ci --include=optional`, `npm run types`, `npm run check`, `npm test`,
`npm run dry-run` in `services/rule-generator`.

The release was checked at desktop and mobile widths, including keyboard tab
navigation, no horizontal overflow, generation against the live API, review/save,
download, browser reload and access-code removal. The API suite runs in the
Workers runtime with mocked provider responses. A separate real API/browser check
confirmed generation with a provider request receipt. Raw responses and private
QA checkpoints remain outside the repository.

Workers fetch uses manual redirects and rejects non-success responses; never
forward authorization to a redirected host. Avoid changing it to `redirect:error`,
which is unsupported by this Workers runtime despite working in Node/browser
fetch. The public service must pass a real generation check after deployment.

Historical evidence is curated in `app/src/data/peace-demo.ts`; preserve quote
limits and provenance. Never add mailbox addresses, original email bytes,
unsubscribe/delivery tokens, private fixture paths or credentials to public data.
