# Remaining real-email answerability review

Prepared September 13, 2026. Preparation made no model requests. After exact
parent review, the 202-call run launched at **23:00:41 UTC**, PID **79995**,
exec session **15847**, and exited successfully at **23:32:46 UTC**.
The full raw audit passed all 202 responses: 200 valid annotations and two
invalid exact-quote responses, leaving **99 of 101 pairs eligible for
adjudication**. No requests were retried and no usage-limit stop occurred.
The process has exited; never restart this attempt set.
This extends the completed 60-pair review to the exact remaining 101 of the 161
natural development pairs. It is exhaustive completion of that existing set,
not a new independent sample or a new prompt-training round.

The extension covers 101 markets, 14 emails, and 22 fact families. All 19 legacy
timing-screen pairs were already included in the first 60, so none remain here.
The prior study's 1,596 files and its plan, raw audit, labels, and label seal are
pinned and preserved. No old helper files or module globals are modified.

The two Astra passes use the original instructions, schema, high reasoning
effort, and complete semantic emails without clipping. Each request includes
only the four original public market fields and the complete email packet.
Prior annotations, regex/Qwen predictions, generated rules, expected outcomes,
payouts, and reserved evaluation data never enter the requests. The two passes
do not see one another's output. Their agreement is correlated model annotation,
not human-validated ground truth.

Exactly 202 jobs are prepared, totaling 1,916,599 known input tokens; the maximum
is 13,735. The original 120,000-token input limit and 20,000-token output reserve
remain, with no hard output cap. Known counts exclude server framing. The usage
snapshot was 62% consumed at 22:57:59 UTC; that does not guarantee remaining
capacity. Existing persistent hosted usage-stop markers remain authoritative.

## Execution and audit gates

The private root is
`~/.local/share/means-of-prediction/slides/real-answerability-remaining-v1-20260913`.
Its prepared plan SHA-256 is
`4abdabd154945c9eb0268c5743b1f31800e6fae0e3be0a94578923eba6060121`.
It pins 26 source/data dependencies, source copies, and the Python/Codex
executables. Thirteen focused tests cover complement identity, blind input
allowlists, full bodies, pass isolation, usage-stop/drain behavior, existing
attempt refusal, exact raw-audit coverage, failed/unknown artifacts, raw output
binding, model identity, and unknown-cost accounting.

From `app/scripts/research/blind`, preparation has already run and must not be
repeated. Verification makes no model requests:

```sh
uv run --python /opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/bin/python3.14 --with tiktoken==0.14.0 python real_answerability_remaining_v1.py verify
```

Before launch, the parent reviews the exact plan, sources, and all 202 request
identities. The private `launch-review.json` must contain `approved: true`, the
exact `planSha256`, and `noCompetingHostedOwner: true`. Only then may the same
pinned command invoke `real_answerability_remaining_v1.py run`.

The completed launch review has SHA-256
`cafb0bf65d4cf51f3b1df7160bc6f1689aeddce68b5f4db2774682da9ee3d505`.
The first eight completed responses passed a separate raw integrity check;
that early check does not establish complete coverage or authorize adjudication.

The completed full raw audit has SHA-256
`32c01acf1a24a901c3d8fdabb7b1336bbfabfc3a477c95936a9d76b0c6211ce5`.
It verifies all 202 unique attempts, complete raw lineage, pinned sources, and
the unchanged prior study. Actual usage was 1,943,429 input tokens and 224,048
output tokens, with 7,662.807 summed request seconds and no missing accounting.
The two invalid responses affect distinct pairs, which must remain unresolved.

Four bounded workers check the shared hosted usage stop before replacements and
before calls. An exclusive attempt marker prevents repeated or uncertain work
from being reused. Already running requests drain after a usage stop; no new
requests follow it. An interrupted runner is never automatically restarted.
No local Qwen inference occurs in this extension.

After the runner finishes and its PID exits, run the separate raw auditor:

```sh
/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/bin/python3.14 real_answerability_remaining_audit_v1.py
```

The auditor checks all 202 planned dispositions, preserves every available
failed/unknown artifact and request hash, rejects duplicate or extra requests,
and reconciles raw service output, model, validation, and usage. Unattempted jobs
remain unattempted; unknown usage/duration remains unknown. `--partial` provides
read-only progress auditing and never grants a completed label gate.

Only pairs with **two raw-verified completed annotations** are eligible for
subsequent explicit semantic adjudication. Failed, uncertain, unattempted, and
invalid annotations leave their pair unresolved. Even complete raw validation
does not establish semantic correctness. The known ordinary-branch versus
future-fallback interpretation issue must be reviewed during adjudication,
without modifying frozen prompts or treating an annotator agreement as proof.

No labels or combined 161-pair method results are created by this runner. Those
require a separately reviewed label seal and a new combined report that preserves
the original 60-pair labels and all unresolved cases. This preparation makes no
claim about population coverage, live contract feasibility, or promotion.

The separate `app/scripts/research/answerability/combined_v1.py` seals explicit
new labels after the full raw gate and then joins the two immutable baselines.
Seven tests and independent code review cover exact cohort/label/raw coverage,
incomplete-review exclusions, quotes, and strict versus factual decisions.
No combined result exists until adjudication and that seal complete.

After the full raw audit, `app/scripts/research/answerability/prepare_review_v1.py`
exports every complete email, original market terms and both annotations to a
private reading directory. It refuses to overwrite existing review material.
The export creates no labels and never loads baseline predictions. Review every
pair explicitly, including annotator agreements, and preserve incomplete pairs
as unresolved before running `combined_v1.py seal`, then `combined_v1.py score`.


The subsequent root adjudication and combined baseline comparison are complete.
See [full findings](REAL-ANSWERABILITY-FULL-V1-FINDINGS.md): the 161-pair union has
one answerable, 157 insufficient and three unresolved pairs. This completion
does not authorize retries, overwrite the original pilot, or promote a model.
