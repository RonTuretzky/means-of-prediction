# Blind generator transport: Claude Fable 5.1 replaces Astra

Status as of September 14, 2026: implemented and unit-tested; no live model
call has been made yet because this machine holds no Anthropic credential.
No new rule draws, prompt optimizations or teacher calls have been run with
the new generator. Every frozen experiment keeps its original Astra artifacts.

## What changed

| Item | Before | Now |
|---|---|---|
| Live generator/teacher | `gpt-6-astra` through the Codex loopback adapter (`astra_transport.py`) | `claude-fable-5-1` through the official Anthropic Python SDK (`fable_transport.py`) |
| Coordinators | `experiment.py` and `improve.py` imported `run` from `astra_transport` | Both import `run` from `fable_transport`; every later round (`round2`–`round4`, `qwen_round1` teacher/rule draws) inherits this through `generate`/`invoke`/`safe_call` |
| Result parsing | `experiment.output_from` read the Codex Responses event shape only | Dispatches on `provider == "anthropic"` to `fable_transport.output_from`; the legacy branch is unchanged for reconciling frozen rounds |
| Frozen-round audits | `round4.py`, `real_answerability_*` and `qwen_hierarchical_optimizer` import `astra_transport.build_request` | Unchanged on purpose. They verify completed Astra artifacts and must keep the Astra request shape and model ID |

The Astra module is not deleted. It is the request-shape witness for the
completed rounds and must stay byte-identical to what their code hashes bind.

## Request shape

`fable_transport.build_request(job)` produces the exact Messages API body
written to `model-request.json` (no authentication material):

```json
{
  "model": "claude-fable-5-1",
  "max_tokens": 64000,
  "system": "<job.instructions>",
  "messages": [{"role": "user", "content": [{"type": "text", "text": "<json.dumps(job.input)>"}]}],
  "output_config": {"effort": "<job.effort>", "format": {"type": "json_schema", "schema": "<job.schema>"}}
}
```

Invariants carried over from the Astra transport and enforced by tests:

- Only the audited job reaches the model: `instructions`, public `input`,
  `schema`, `effort`, optional `maxOutputTokens`. Inherited keys such as
  `tools`, `messages`, `temperature`, `thinking` are dropped by construction.
- No tools, no `tool_choice`, no sampling parameters, no assistant prefill.
  Thinking is always on for this model and is not configured by the transport.
- `max_tokens` is required by the API. When a job carries no
  `maxOutputTokens` the transport uses 64,000 and records both the requested
  and effective values. The archived rounds' "guidance, not a cap" wording
  still applies to the instruction text; the effective cap is now explicit.
- Effort names are the same five levels the pilots used: `low`, `medium`,
  `high`, `xhigh`, `max`. Any other value is rejected before a request is built.
- No server-side model fallback is configured. A safety-classifier or model
  refusal returns `stop_reason: "refusal"`, which the transport records as the
  terminal status `refusal` with `stop_details`. Silently serving a draw from
  another model would change the generator identity bound into the artifacts,
  so refusals are retained as receipts rather than rescued.
- `max_retries=0` on the client. Every attempt is one recorded request. Any
  same-input retry is a coordinator decision under a declared recovery policy,
  as before.

## Artifacts per request

| File | Contents |
|---|---|
| `model-request.json` | Exact request body; its SHA-256 is recorded in `requests[].requestSha256` |
| `process.json` | PID of the calling process, start time, model. Used by the coordinators' interrupted-run guard |
| `transport-checkpoint.json` | Progressive state, written before and after the request |
| `transport-result.json` | Final state: `provider`, `model`, `requests` (status, request ID, hash), `events` (the full message as a dict, thinking blocks reduced to `{"type": "thinking"}` because their text is not returned), `stopReason`, `stopDetails`, `serviceErrors`, `transportErrors`, `seconds`, `requestedMaxOutputTokens`, `effectiveMaxTokens` |
| `output.txt` | Raw text of the message, kept for the same recovery path the legacy parser used |

Statuses returned by `output_from`: `completed` (`end_turn` with valid
JSON), `incomplete` (`max_tokens`), `refusal`, `invalid_json`,
`model_mismatch`, `transport_failed`, or the raw stop reason for anything
else. Only `completed` yields an output object. Usage keys are the API's
`input_tokens` / `output_tokens` plus cache counters, so existing usage
accounting keeps working.

Rate-limit receipts differ from the Astra service: an Anthropic 429 body has
`error.type == "rate_limit_error"`, not `usage_limit_reached`. The archived
`qwen_capacity_recovery.usage_limited` check therefore does not recognise it.
Declare a new recovery policy before any same-input retry against this
transport rather than widening the old check silently.

## Credentials and runtime

- Credential lookup order: `ANTHROPIC_API_KEY` in the environment, then
  `apiKey` in `~/.config/means-of-prediction/anthropic.json` (mode 0600).
  Neither value is ever written into an artifact; a missing credential is
  recorded as a `transportErrors` receipt.
- Claude Fable 5.1 requires 30-day data retention on the organisation. A
  zero-data-retention organisation gets `400 invalid_request_error` on every
  request; check retention before debugging the payload.
- Python runtime: `/Users/wk/.local/share/means-of-prediction/venv-research-py314`
  (Python 3.14.6, `anthropic` 1.5.0, `tiktoken` 0.14.0, `pycryptodome` 3.23.0).
  Homebrew's Python refuses package installs, and the archived scripts need
  `tiktoken`, so use this interpreter for research commands.

## Commands

```sh
cd app/scripts/research/blind
V=/Users/wk/.local/share/means-of-prediction/venv-research-py314/bin/python
$V -m unittest test_fable_transport -v
$V -m unittest discover -s . -p 'test_*.py'
# Synthetic credential/shape check; writes a receipt, not research data.
$V fable_transport.py --smoke ~/.local/share/means-of-prediction/fable-transport-smoke-20260914/attempt-2
```

The first smoke attempt (`attempt-1`) is retained as a missing-credential
receipt. Run a new attempt directory once a key is in place; do not overwrite it.

## Before the first real Fable draw

1. A successful smoke run with a recorded 200 status and `end_turn`.
2. A new private root for the round (for example
   `slides/fable-qwen-nyt-round1-<date>`). Completed Astra rounds are closed
   and their caches return Astra outputs for identical jobs; never point a
   Fable run at an old root.
3. An effort sweep that includes `low` and `medium`. Lower effort on this
   model often matches or exceeds the old `xhigh` arms, and the prompts
   written for Astra are likely too prescriptive; A/B a de-prescribed prompt
   before adopting one.
4. Token accounting for context checks through the API's `count_tokens`,
   not `tiktoken`, when the V3 hierarchy helpers are ever revived.

None of this changes the judge. The pinned local Qwen3.5-35B-A3B judge,
its runtime seal and the protected evaluation reservations are untouched.
