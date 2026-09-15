# Blind generator transport: Claude Fable 5.1 replaces Astra

Status as of September 14, 2026: implemented, unit-tested and verified live.
The generator runs through the installed Claude Code sign-in, exactly as the
Astra transport ran through the installed Codex sign-in. No API key and no
credential file are involved. The first live smoke call completed with a
schema-validated answer, generator identity `claude-fable-5-1`, and a
recorded cost of about three cents.

## What changed

| Item | Before | Now |
|---|---|---|
| Live generator/teacher | `gpt-6-astra` through `codex exec` and a loopback adapter (`astra_transport.py`) | `claude-fable-5-1` through headless Claude Code (`claude -p`) in `fable_transport.py` |
| Coordinators | `experiment.py` and `improve.py` imported `run` from `astra_transport` | Both import `run` from `fable_transport`; every later round (`round2`–`round4`, `qwen_round1` teacher and rule draws) inherits this through `generate`/`invoke`/`safe_call` |
| Result parsing | `experiment.output_from` read the Codex Responses event shape only | Dispatches on `provider` to `fable_transport.output_from`; the legacy branch is unchanged for reconciling frozen rounds |
| Frozen-round audits | `round4.py`, `real_answerability_*` and `qwen_hierarchical_optimizer` import `astra_transport.build_request` | Unchanged on purpose. They verify completed Astra artifacts and must keep the Astra request shape and model ID |

The Astra module is not deleted. It is the request-shape witness for the
completed rounds and must stay byte-identical to what their code hashes bind.

## How a request is made

`fable_transport.build_request(job)` freezes the request written to
`model-request.json`: model, effort, the job's instructions as the system
prompt, the JSON of the job's input as the single user turn, the JSON schema,
an empty tool list, one turn, the token guidance (informational; the CLI has
no output cap flag) and a per-call dollar cap. The argument vector is part of
the frozen request:

```
claude -p --model claude-fable-5-1 --effort <effort> --output-format json
       --system-prompt <instructions> --json-schema <schema>
       --tools "" --max-turns 1 --max-budget-usd <cap>
       --no-session-persistence --setting-sources "" --strict-mcp-config
       --disable-slash-commands
```

The child process runs in a fresh empty temporary directory with the calling
session's binding variables removed from its environment, so it has no
repository, no project or user settings, no hooks, no MCP servers, no memory
files, no saved session and no tools. `--system-prompt` replaces Claude
Code's default system prompt entirely, which is why a call costs about a
thousand input tokens instead of eighteen thousand. Output is validated
against the job schema by the CLI and returned as `structured_output`.

Residual context, verified by a transparency probe: the harness prepends a
reminder carrying the signed-in user's email address and appends an
environment block with the temporary directory, platform, model identity and
today's date. No memory, workspace or evidence text was present. Claude Code
also makes one small Haiku side-call per run for session bookkeeping; it is
recorded under `modelUsage` and does not produce the answer. The generator
identity check requires exactly one non-Haiku model in `modelUsage`, and it
must be `claude-fable-5-1`.

Invariants carried over from the Astra transport and enforced by tests:

- Only the audited job reaches the model. Inherited keys such as `tools`,
  `messages`, `temperature`, `thinking` are dropped by construction.
- No sampling parameters, no prefill, no fallback model. Thinking is always
  on for this model and is not configured by the transport. Efforts are
  `low`, `medium`, `high`, `xhigh`, `max`; anything else is rejected.
- A refusal (`stop_reason: refusal`) is the terminal status `refusal`, kept as
  a receipt. Budget or turn errors keep the CLI's `subtype` as the status.
- Every attempt is one recorded request. The transport never retries; a
  same-input retry is a coordinator decision under a declared recovery
  policy, as before.
- `MOP_FABLE_MAX_BUDGET_USD` (default 8) caps one call; a job can set its own
  `maxBudgetUsd`. `MOP_FABLE_TIMEOUT_SECONDS` (default 1800) bounds wall
  time; a timeout kills the child and is recorded. `MOP_CLAUDE_CODE_BIN`
  selects the executable, else `CLAUDE_CODE_EXECPATH`, else `claude` on PATH.

## Artifacts per request

| File | Contents |
|---|---|
| `model-request.json` | Frozen request including `argv`; its SHA-256 is in `requests[].requestSha256` |
| `process.json` | PID of the child, start time, model. Used by the coordinators' interrupted-run guard |
| `client-output.json`, `client-stderr.log` | Raw stdout and stderr of the child |
| `transport-checkpoint.json` | Progressive state, written before and after the request |
| `transport-result.json` | Final state: `provider`, `model`, `executable`, `requests` (exit code, ok/error, session ID, hash), `events` (the CLI result envelope with `structured_output`, `usage`, `modelUsage`, `total_cost_usd`, `stop_reason`, `subtype`, plus the derived `model`), `stopReason`, `subtype`, `costUsd`, `serviceErrors`, `transportErrors`, `seconds` |
| `output.txt` | The result text, kept for the legacy recovery path |

Statuses from `output_from`: `completed` (success envelope with a validated
output), `refusal`, `invalid_json`, `model_mismatch`, `transport_failed`, or
the CLI's error subtype such as `error_max_budget_usd` or `error_max_turns`.
Only `completed` yields an output object. Usage keys are `input_tokens`,
`output_tokens` and the cache counters, so existing accounting still works.

Rate-limit receipts differ from the Astra service. The archived
`qwen_capacity_recovery.usage_limited` check looks for `usage_limit_reached`
and will not recognise a Claude sign-in limit; declare a new recovery policy
before any same-input retry against this transport.

## Runtime

Python: `/Users/wk/.local/share/means-of-prediction/venv-research-py314`
(Python 3.14.6 with `tiktoken` 0.14.0 and `pycryptodome` 3.23.0, which the
archived scripts need; Homebrew's Python refuses package installs).

```sh
cd app/scripts/research/blind
V=/Users/wk/.local/share/means-of-prediction/venv-research-py314/bin/python
$V -m unittest test_fable_transport -v
$V -m unittest discover -s . -p 'test_*.py'
# Synthetic sign-in/shape check; writes a receipt, not research data.
$V fable_transport.py --smoke ~/.local/share/means-of-prediction/fable-transport-smoke-20260914/attempt-3
```

Smoke receipts so far: `attempt-1` (earlier SDK backend, missing credential)
and `attempt-2` (CLI backend, completed). Use a new attempt directory each
time; never overwrite one.

## Before a real Fable round

1. A new private root for the round. Completed Astra rounds are closed and
   their caches return Astra outputs for identical jobs; never point a Fable
   run at an old root.
2. An effort sweep that includes `low` and `medium`. Lower effort on this
   model often matches the old `xhigh` arms, and prompts written for Astra
   are likely too prescriptive; A/B a de-prescribed prompt before adopting.
3. The judge is unchanged: the pinned local Qwen3.5-35B-A3B, its runtime seal
   and the protected evaluation reservations are untouched.
