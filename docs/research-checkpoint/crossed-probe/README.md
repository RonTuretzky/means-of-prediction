# Crossed rule/judge diagnostic

This small development diagnostic crosses the baseline and V3 frozen Astra
rules with the baseline and V3 Qwen judge prompts. The same twelve previously
reviewed cases give 48 planned rows. Failed rules remain unavailable; they do
not cause replacement draws or substituted cases.

The panel and cyclic execution order were fixed before inspecting V3 outputs.
Each variant appears three times in each position; this is position balance,
not complete carryover balance. Four case blocks run concurrently, with each
block's four calls sequential. The full email, metadata, model, schema, seed,
sampling and output cap remain unchanged. Only the frozen rule and system
prompt are crossed. Repeated baseline and V3 cells are compared with their
earlier benchmark records, because deterministic settings do not guarantee
identical inference.

Run from the original private directory, never this source archive:

1. After all 241 V3 rule records are frozen, run `python3 probe.py prepare`.
   It verifies rule provenance, freezes exact full requests and reads no V3
   judgments. Independently review the exact input freeze and record
   `reviewed.json` with `approved` and `inputFreezeSha256`.
2. Only after complete V3 local evaluation, explicit local release, completed
   basis diagnostic, and verified model quiescence, record `run-approved.json`.
   It binds the input freeze, review, V2/V3 complete judgments, V3 local release
   and basis summary hashes, plus `localInferenceQuiescent: true`.
3. Run `python3 probe.py preflight`, then `python3 probe.py run`. All actual
   inputs must fit in full. Started or uncertain attempts are never retried
   automatically; preserve capped and failed responses.
4. Read all changed answers and their evidence. Report full and common-case
   comparisons, replay agreement, token usage, and missing observations.

This is a selected old-development panel with one frozen draw per generator,
not an independent accuracy estimate or population settlement percentage. It
cannot automatically replace the main method or trigger selection. All raw
emails, labels, requests, responses and private manifests stay outside Git.

`basis_audit_support.py` is an exact copy of the reviewed basis helper. Only its
raw-response validator is used, selecting the unchanged original schema; no
stored output or final answer is repaired. `order_support.py` and the source
closure are likewise preserved. The request, scoring and runtime-validation
functions match the active study.
