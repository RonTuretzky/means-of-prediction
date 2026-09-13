This is a private diagnostic of JSON output order, using 12 existing development cases. It compares the original order with an order that places `evidenceQuote` first. The fields, rule, full email, prompt, model, sampling settings, and score definitions stay the same. It makes 24 local calls and generates no new Astra rules.

The panel deliberately includes both prior successes and prior errors. It is a diagnostic panel, not an independent accuracy estimate. A promising result requires a separately declared full evaluation before any selection. No reserved email or fixture is opened here.

Preparation is complete. The original `input-freeze.json` remains unchanged. `reporting-amendment-v1.json` preserves the two original reporting source files and binds their reviewed replacements. All 24 saved wire requests still match the original freeze. Eight synthetic checks pass; `reviewed.json` records the independent code review.

No token preflight or inference has run. Wait for all 1,915 v2 local judgments and its summary, then coordinate with the Qwen task to confirm no other inference is running. Create `run-approved.json` with the current timestamp, `inputFreezeSha256`, `reviewSha256`, `v2JudgmentsSha256`, and `localInferenceQuiescent: true`. This is an internal coordination record, not a request for user approval. Do not create it while the model is busy or after final study selection.

Then execute, in order:

```sh
python3 probe.py preflight
python3 probe.py run
```

The run transmits each saved `request-wire.json` byte for byte. It runs four case pairs concurrently; half start with each variant. A completed result can be reused on recovery, but an uncertain started request blocks all new calls until reconciled. The final summary checks raw responses, requested versus actual field order, exact input token counts, replay variation, validity, accuracy diagnostics, and independent missing usage fields. Inference costs belong in a separate probe bucket when reporting the combined experiment.
