# Rule generator API

Small authenticated Cloudflare Worker for DeepSeek rule drafts. The React website stays on GitHub Pages. The browser receives a validated draft and a provider receipt; provider credentials never enter the frontend bundle.

## Run locally

```sh
npm ci --include=optional
npm run types
```

Create an ignored, owner-only `.dev.vars` containing `DEEPSEEK_API_KEY` and a separate random `RULE_GENERATOR_TOKEN` of at least 32 characters. Never commit this file. Run `npm run dev`, then start the frontend with `VITE_RULE_API_URL=http://127.0.0.1:8787`. Enter the **operator token**, not the provider API key, in Rule Studio. The frontend retains it only in page memory.

```sh
npm run check
npm test
npm run dry-run
npx wrangler deploy --secrets-file .dev.vars
```

Set the deployed HTTPS URL in the Pages workflow's `VITE_RULE_API_URL`. Use Wrangler secrets to rotate either credential. Generated environment/runtime declarations are ignored; regenerate after changing the configuration. The pinned npm lock includes platform-specific optional runtime dependencies.

## Contract and safeguards

`POST /v1/rules`, with `Authorization: Bearer <operator token>` and JSON `{question, context, deadline}`. The deadline must be an ISO timestamp with a timezone. Success returns `{draft, receipt}` using the browser-safe types and validator in `src/schema.ts`.

Requests use an explicit CORS allowlist, a shared operator-token rate-limit key (6 requests/minute per Cloudflare location), a 24 KiB request bound, a 64 KiB provider-response bound, 2,500 output tokens, a 60-second provider timeout, and no automatic retries. This rate limit is abuse reduction, not a globally exact spending cap; retain provider-side budgets. Authentication and unavailable configuration fail closed. Raw email/MIME headers are rejected. The API does not fetch user URLs, browse, run tools, write subscriptions, send mail, submit transactions, or log prompts, provider responses or credentials. Provider failures are returned as generic errors.

The server validates output structure and fixed question/deadline identity. This is **not semantic certification** of an AI-generated rule. Human review remains required. The prompt distinguishes Google's email signature from the linked publisher, event time from delivery time, query text from evidence, complementary evidence from unsupported concatenation, and absent evidence from NO. A provider receipt identifies a generation call; it is not a cryptographic attestation or a settlement result.

The UI saves reviewed plans in browser storage and exports a canonical SHA-256 commitment. These plans do not deploy markets or automatically register Google Alerts. The historical Nobel replay imported existing Polymarket rules and remains separate from generated drafts and the partial Sepolia computation demo.
