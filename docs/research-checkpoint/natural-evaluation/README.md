# Supplemental comparison on two new NYT emails

The evaluator is prepared using safe source schemas only. **The reserved email bodies and pair annotations are still unopened.** This is a private research supplement; it neither trains weights nor executes settlements.

The fixed design evaluates all 241 existing public questions against each of two new emails. It compares the frozen regex baseline with the unique Qwen baseline and final selected method, using existing generated rules with their original failures. Two documents give 482 pairs, not 482 independent observations. These public questions have already been used in development.

`protocol.json` and `procedure.json` define representations, metadata, failure handling and scoring. `evaluation_core.py` verifies integrity and annotations. `evaluate.py` orchestrates frozen sources, exact requests, local inference and scoring. `preflight.mjs` counts full rendered input tokens without inference. The pure regex modules are byte-identical copies from the completed regex study.

The adapter cannot freeze or open the reservation until the Qwen final selection and all 48 separate independent-test Astra draws exist and verify. The two-email annotation file is read only after every selected method has all 482 prediction records. Ambiguity, nonbinary conditions, failures and conflicts remain visible. Exact quote matching is an additional diagnostic, not an entailment check.

All output stays in this directory with private permissions. Every prediction call is isolated and retained; no retries or best-of sampling. A started call without a final result requires explicit reconciliation. No prompt optimization or method selection may use these results after opening.

Execution order, after the current Qwen study is selected and its original independent rule draws are frozen:

```sh
python3 evaluate.py freeze
python3 evaluate.py prepare
python3 evaluate.py regex
python3 evaluate.py qwen --method baseline
# Run once for the selected Qwen method too, if it differs from baseline.
python3 evaluate.py score
```

Run Qwen only when the main study's inference jobs are finished, to preserve runtime and latency accounting. This evaluator reuses the exact selected study's sealed model request and semantic renderer. It does not switch models, quantization, generation settings or onchain contracts.

The recorded signature pass is the earlier intake observation. This evaluator checks frozen raw/decoded/body-hash provenance and signature linkage; it does not repeat RSA verification or public-key lookup. Neither DKIM authentication nor a factual report establishes every original settlement condition.
