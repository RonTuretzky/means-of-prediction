# Research procedure checkpoint

These are byte-for-byte source snapshots of the private experiment procedures on
2026-09-13. The manifest records each original absolute path and SHA256. The active
experiment remains in its original private directories; these copies do not
replace or amend any existing input seal.

Only source code, synthetic unit tests, generic diagnostic prompts, and procedure
documents are included. Emails, model requests/responses, private labels, learned
per-market rules, credentials, and sealed evaluation data are intentionally absent.

Do not execute these archival copies in this directory: several procedures resolve
their artifact root relative to their own file. Continue from the original paths
in [the handoff](../QWEN-RESUME-HANDOFF.md). If restoring onto another machine, copy
the private artifacts separately through private storage, verify all seals, and
record a relocation amendment before changing any path-sensitive procedure.

The snapshots include the quote-order probe, the strict-only split-predicate
probe, the supplemental natural-email evaluator, and the offline development
comparator. The shared main harness lives in `app/scripts/research/blind/`.
