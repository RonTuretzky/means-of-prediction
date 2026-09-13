# Checkpoint validation — 2026-09-13

This is a local source/process checkpoint, not a release or a new accuracy result.

- Main research suite: `python3 -m unittest discover -s app/scripts/research/blind -p 'test_*.py'` — 86 passed.
- Research JavaScript tests: `pnpm test:scripts` — passed (10 tests).
- Body proof tests: `pnpm test:body` — passed (7 tests).
- Automation tests: `pnpm test:automation` — passed.
- App: `pnpm build` — passed; existing dependency-annotation and large-chunk warnings remain.
- All 49 archival procedure files match both their original private source bytes and the SHA256 source manifest.
- Order and predicate probes previously passed eight synthetic tests each; the supplemental evaluator passed 23. None of their model calls or reserved-data evaluations were started for this checkpoint.
- `git diff --cached --check` — passed.
- Staged-content scan found no credential-token patterns, pasted Gmail secret, literal secret assignments, private-key blocks, or private email/result/cache file names. This is a targeted checkpoint check, not a comprehensive security audit.

The full `forge test --ffi` contract suite completed successfully: **170 tests
passed across 14 suites, zero failures and zero skipped**, including all 18
LLMJudge tests. Wall time was 223.06 seconds. The original validation process
(PID 11137, execution session 28818) exited successfully.

No live deployment or browser E2E run was performed as part of this save request.
