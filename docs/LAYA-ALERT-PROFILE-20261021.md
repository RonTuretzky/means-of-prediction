# Google Alerts student-base support profile (2026-10-21)

The active demo must use a genuine Google Alerts email/result and the recommended
final student-base artifact. No inference or training was run for this review.
Only code, configuration and aggregate evaluation reports were read; no held-out
or calibration rows were inspected or selected.

## Exact support semantics

`ALERT_STUDENT_BASE_SUPPORT_V1` (ID 3) is independent support at 0.55:

```text
supportsA = pA >= 0.55
supportsB = pB >= 0.55
```

| A score | B score | supportsA | supportsB |
|---|---|---|---|
| 0.5499 | 0.5499 | false | false |
| 0.5500 | 0.5499 | true | false |
| 0.5499 | 0.5500 | false | true |
| 0.5500 | 0.5500 | true | true |
| 0.6000 | 0.8000 | true | true |

There is no larger-score comparison, A-on-tie rule or both-positive abstention in
the alert table/forward paths. Both flags can be true; both can be false. Neither
case determines settlement. The scaffold exposes supportFlags and has no exclusive
candidate API. Scores/model execution remain unauthenticated.

Code evidence:

- `alerts_tables.py:3,30-33`: YES support is pA >= t, independent of pB. Count
  distinct host values, optionally intersected with the registry allowlist, at K=1/2/3.
- `alerts_student.py:235-236`: forward summary independently counts markets with
  any A score at threshold and markets with any B score at threshold.
- `alerts_forward.py:121-126`: independently append qualifying sides and count
  hosts for each. Its legacy fallback to pQuestion when pA is absent is excluded
  from this profile: explicit factual A/B predicates and both scores are required.
- `alerts_student.py:204-205`: calibration uses max(pA,pB) >= t on teacher-negative
  calibration units and selects the first tested threshold meeting the configured
  false-fire ceiling. This is threshold selection, not an exclusive verdict.
- `HANDOFF-ALERT-STUDENT-20261021.md:26,53-55,62-65`: threshold 0.55; recommended
  final student-base root. Jev's 0.7 is a separate reader threshold.

## Exact input construction

`alerts_student.py:36,50-65` defines the student input path:

```text
h = cut(result.headline, 110)
subject = h
body = h + "\n" + (result.publisher or result.host) + "\n" + cut(result.snippet, 162)
state = {"subject": subject, "body": body}
```

cut(s,n) first applies (s or '').strip(). Return unchanged if Python character
length <= n. Otherwise take the first n-4 characters, find the last ASCII space,
retain text before that space only if its position > n//2, apply rstrip(), and append
exactly ` ...`. These are Python Unicode character operations, not UTF-8 byte
counts. The publisher has no further truncation here. headline_only=False is required.

The model subject is the result headline, not the email Subject/query banner.
Google's publisher display label is model text; only an empty/falsy label falls
back to the article host. Outlet identity/K counting use article URL host, never
publisher label or headline suffix. `alerts_email.py:1-7,11-13,23-54` extracts Google
redirect url= targets and reduces hosts with a pinned hand-written two-label-suffix
set, not a full Public Suffix List. Freeze that algorithm and admissible redirects.

The currently dirty alerts_email.py contains schema.org News and visible Web
extraction. Preserve it and freeze its exact source for the selected branch. This
review does not establish that all Google Alerts MIME formats are supported.

Each side's noul instruction is:

```text
Does the text state, as something that has already happened: {factualSide[:600]} Forecasts, odds, plans, hypotheticals, denials and quoted predictions do not count.
```

questions() also creates diagnostic q. Training has withQ=False, no choice head,
and only A/B targets (`alerts_student.py:165-171`). Evaluation passes q/A/B to Agent,
but support counts use A/B. Freeze whether the demo retains that three-question
batch or deliberately uses A/B only. Maximum combined lengths are 960 for q/A/B
or 640 for A/B; each independent sequence remains capped at 320.

Legacy alerts_forward.unit_state (line 19) applies no cuts. The alert-student's
forward evaluation (lines 232-236) calls the cut-aware student unit_state. Use the
cut-aware path here, not the legacy helper with an equivalence assumption.

## Tokens and calibrated probabilities

Final-root config and prepare metadata specify max_len=320, head_max_len=160.
Agent reads these values (`laya/agent.py:280-286`). Installed laya/common.py:49-86
constructs each sequence:

```text
[CLS] noul question: {instructions} [SEP]
[MASK] false: no, the statement does not hold
[MASK] true: yes, the statement holds [SEP]
{JSON-serialized state} [SEP]
```

Pin tokenizer calls/special IDs and marker indices. Each option starts with a mask
and at most 48 option IDs; instruction budget comes from head_max_len. State is
right-truncated to remaining max_len room (truncate_left=False). Serialization is
Python json.dumps(state, ensure_ascii=False), default spaces, subject-before-body
insertion order. Literal mask-token strings are replaced with spaces before
tokenization. Freeze actual tokens, padding/masks, boundaries and truncation report;
total token count proves none of these semantics.

Recommended final base uses noul:2 temperature **1.1089085340499878**. Agent selects
that options-bucket temperature before softmax and returns true-option probability
rounded to four decimals (`agent.py:329-332,357-360`). Parse that decimal exactly and
multiply by 1000000 for ppm; 0.55 is 550000 ppm. Do not use confidence, action
probability, choice head or an unrounded probability instead.

## Artifact identity and calibration gate

Recommended root:
`/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/student-base`.

Read-only checks on October 21:

- Final-root and raw checkpoint_epoch1/model.safetensors are identical:
  1685197088 bytes, SHA-256
  `5ed8ce354cb1bf9f313fb4791f74601acbf955598d74f8d6742da3497aee5169`.
- Final rl_agent_config.json SHA-256:
  `c388a2873fe58de011fbe58a27f6553a713f15f8c613c829227097bd2a6332ec`;
  noul:2 temperature 1.1089085340499878.
- Raw checkpoint config SHA-256:
  `a83b7896bfda813a7a2e7e602ab0fe04d6f61919e71e8dc31f3002dd41b6c7d9`;
  noul:2 temperature 1.983399510383606 despite the fallback array's 1.0.
  Agent gives the options bucket precedence.
- eval-student-base-checkpoint_epoch1.json SHA-256:
  `8641d538630a39eefbd6c1b0e6db543f0fc9b7999b8454be38b0d61df2909ab1`;
  records raw checkpoint path, threshold 0.55, 4000 calibration units, aggregate
  calibration false-fire [0.00209,3820]. No underlying rows were read.

The chosen demo artifact is the recommended final student-base root above, with
its fitted 1.1089085340499878 temperature and 0.55 profile, frozen without tuning.
The raw checkpoint is not the chosen model configuration. The raw-path report does not prove
calibration/accuracy equivalence for the different final-root temperature.
Identical weights do not close this gate. No new accuracy claim is made here.

## State eligibility and remaining gates

Eligible frozen input needs real Google Alerts mail/result; complete authenticated
header/body material; exact selection and HTML/entity/whitespace processing;
headline/publisher/snippet and target/host; full A/B rules; source/K/date/timeout
policy; exact final-root/config; and schema/tokenization/mask/truncation pins.
Do not select examples or predicates after inspecting model outputs.

Google DKIM authenticates Google's email, not the linked publisher/event. Distinct
hosts in one email are host-support observations, not different newspaper signers.
Request/source/nullifier aggregation must reflect that; existing market source
counting cannot be reused by relabeling fields.

The binding now requires GoogleAlertBodyParser v2, described below. Unsupported
real-alert MIME/encoding remains ineligible. Never silently strip/rewrite signed
bytes. Commitments alone verify neither semantic extraction nor canonical tokens,
inference, certificates or settlement.

## Google MIME parser v2 interface and integration boundary

The inspected pure interface is
`GoogleAlertBodyParser.verify(header, canonicalBody, encodedOffset, encodedLength, decodedExcerpt)`.
It returns bool and has VERSION=2. It authenticates the complete canonical body
against bh= under a separately RSA-authenticated canonical header; it does not
verify RSA, prove Google provenance, select an article, strip HTML or tokenize input.

The fixed profile is multipart/alternative with exactly plain/base64 followed by
HTML/quoted-printable. The signed top-level Content-Type must have exactly one
boundary and be named exactly once in DKIM h=. The parser validates supported
charset/part headers and payload encoding, with no preamble/epilogue, nesting,
folded part headers or additional unsupported headers/parameters. The window must
lie entirely inside the encoded HTML payload; offsets refer to the complete body,
not decoded HTML. Selected QP escapes must decode exactly to bodyExcerpt. Full
body is capped at 196608 bytes, window at 4096; DKIM l= truncation is refused.

LayaRequest now requires parserVersion=2 and directly dispatches evidence validation
to that interface, preserving full-body SHA-256, exact EmailProof, encoded window
and decoded-excerpt commitments. Versions 1/3 and unsupported single-part bodies
are rejected. Synthetic multipart tests exercise the interface without an RSA claim.
The parser's own source files were not edited for this integration.

Next consumer boundary: DKIMVerifier still advertises bodyParsingVersion()=1 and
calls its single-part parser. An authenticated Google-mail adapter must explicitly
combine its real RSA/header/nullifier/domain/date checks with the v2 body check,
without weakening either. Do not treat validateEvidence or the v2 parser alone as
email authentication. A real frozen Google MIME fixture plus tamper tests and
source/HTML/model-input semantic binding are required before claiming integration
acceptance; this review does not perform inference or market settlement.

## Post-run temperature sensitivity

The final root and its fitted temperature were chosen and frozen before inference
from the explicit handoff recommendation. No model/profile/threshold was changed
or tuned after observing outputs. The completed local reference reported 30 layers
and exact agreement with stock replay. At the chosen temperature 1.1089085340499878,
rounded outputs were q=0.4402, A=0.5846, B=0.0318: supportsA=true, supportsB=false.

Recomputing the same captured logits with the raw checkpoint's temperature
1.983399510383606 yielded q=0.4664, A=0.5476, B=0.1291: both support flags are false
at the unchanged 0.55 threshold. q is diagnostic only. This sensitivity materially
changes this candidate's A support and confirms that the calibration attribution
gap cannot be dismissed because the weights match. It establishes no new accuracy
claim, authenticated inference certificate or market settlement.

Source tokenizer metadata identified TokenizersBackend. The run used a private
runtime copy with exactly Agent's tokenizer compatibility fix; source and runtime
metadata hashes were both pinned. The original tokenizer artifact was unchanged.
