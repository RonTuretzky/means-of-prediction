"""A single isolated Claude Fable 5.1 response through the installed Claude Code sign-in.

This is the live blind generator transport. It replaces the Codex/Astra
loopback adapter (``astra_transport.py``) for every new rule draw, prompt
optimization and teacher call. The Astra module stays in place, unchanged, so
frozen experiment artifacts can still be reconciled against their original
request shape.

Like the Astra transport used ``codex exec`` with the user's Codex sign-in,
this one runs Claude Code headless (``claude -p``) with the user's Claude
sign-in. No API key or credential file is involved; nothing is stored here.

Invariants shared with the Astra transport:

* The request is built only from an explicit, audited job (instructions,
  public input, JSON schema, effort). The child runs in an empty temporary
  directory with no repository, no project/user settings, no MCP servers,
  no slash commands, no session persistence and an empty tool list, so the
  coordinator's workspace, conversation history and private evidence never
  reach the generation model.
* The system prompt is exactly the job's instructions (``--system-prompt``
  replaces Claude Code's default prompt). The user turn is exactly the JSON
  of the job's input. Output is schema-validated by ``--json-schema``.
* No sampling parameters, no assistant prefill, no model fallback. Thinking
  is always on for this model; depth is the job's ``effort``.
* The exact request (including the argument vector) is written to
  ``model-request.json``; its SHA-256 is recorded with the child's exit
  status. Raw stdout/stderr, token accounting and cost are retained. Failures
  and refusals are retained as receipts; the transport never retries.
* A per-call dollar cap (``--max-budget-usd``) bounds unattended runs.

Residual context the harness adds to every headless call, verified by a
transparency probe on 2026-09-14: a reminder carrying the signed-in user's
email address, and an environment block with the temporary directory, the
platform, the model identity and today's date. No memory files, CLAUDE.md
content or workspace text were present. Claude Code also makes one small
Haiku side-call per run (session bookkeeping); it is recorded in
``modelUsage`` and does not contribute to the generated output.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile, time
from pathlib import Path

MODEL = 'claude-fable-5-1'
PROVIDER = 'claude-code-cli'
EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')
DEFAULT_MAX_BUDGET_USD = float(os.environ.get('MOP_FABLE_MAX_BUDGET_USD', '8'))
TIMEOUT_SECONDS = float(os.environ.get('MOP_FABLE_TIMEOUT_SECONDS', '1800'))
# Sign-in usage limits are gates, not model answers. Under the 'wait' policy a
# limited call sleeps until the reset named in the receipt and submits the same
# frozen request again; every attempt is recorded. 'stop' keeps the single receipt.
LIMIT_POLICY = os.environ.get('MOP_FABLE_LIMIT_POLICY', 'wait')
MAX_LIMIT_WAITS = int(os.environ.get('MOP_FABLE_MAX_LIMIT_WAITS', '4'))
MAX_LIMIT_WAIT_SECONDS = float(os.environ.get('MOP_FABLE_MAX_LIMIT_WAIT_SECONDS', str(6*3600)))
LIMIT_GATE = Path(os.environ.get('MOP_FABLE_LIMIT_GATE', str(Path.home()/'.local/share/means-of-prediction/fable-hosted-limit-gate.json')))
UNKNOWN_RESET_WAIT_SECONDS = 900.0
RESET_GRACE_SECONDS = 120.0
# Session-binding variables of the calling Claude Code process; the child must not inherit them.
STRIP_ENV = {'CLAUDECODE', 'CLAUDE_CODE_ENTRYPOINT', 'CLAUDE_CODE_SESSION_ID', 'CLAUDE_CODE_CHILD_SESSION',
             'CLAUDE_CODE_MESSAGING_SOCKET', 'CLAUDE_CODE_MESSAGING_TOKEN', 'CLAUDE_PID', 'CLAUDE_CODE_EMIT_SESSION_STATE_EVENTS'}

def executable():
    for candidate in [os.environ.get('MOP_CLAUDE_CODE_BIN'), os.environ.get('CLAUDE_CODE_EXECPATH'), shutil.which('claude')]:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError('No Claude Code executable: set MOP_CLAUDE_CODE_BIN or install claude')

def build_request(job):
    """Exact headless request for one blind job. Contains no credentials."""
    effort = job.get('effort', 'high')
    if effort not in EFFORTS:
        raise ValueError('Unsupported effort for ' + MODEL + ': ' + str(effort))
    request = {
        'model': MODEL, 'effort': effort,
        'system': job['instructions'],
        'input': json.dumps(job['input'], ensure_ascii=False),
        'schema': job['schema'],
        'tools': [], 'maxTurns': 1,
        'maxOutputTokensGuidance': job.get('maxOutputTokens'),
        'maxBudgetUsd': job.get('maxBudgetUsd', DEFAULT_MAX_BUDGET_USD),
    }
    # Inherited job keys such as tools/messages/temperature are dropped by construction.
    request['argv'] = argv(request)
    return request

def argv(request):
    """Argument vector after the executable. Frozen with the request for auditing."""
    return ['-p', '--model', request['model'], '--effort', request['effort'], '--output-format', 'json',
            '--system-prompt', request['system'], '--json-schema', json.dumps(request['schema'], ensure_ascii=False),
            '--tools', '', '--max-turns', str(request['maxTurns']), '--max-budget-usd', str(request['maxBudgetUsd']),
            '--no-session-persistence', '--setting-sources', '', '--strict-mcp-config', '--disable-slash-commands']

def child_env():
    env = {k: v for k, v in os.environ.items() if k not in STRIP_ENV}
    env.pop('MOP_FABLE_MAX_BUDGET_USD', None)
    return env

def generation_model(result):
    """The non-bookkeeping model that produced the answer, from Claude Code's per-model usage."""
    models = [m for m in result.get('modelUsage', {}) if not m.startswith('claude-haiku')]
    if len(models) == 1:
        return models[0]
    return None if not models else 'ambiguous:' + ','.join(sorted(models))

def event_from(result):
    """Retain the result envelope; add the generator identity for output_from."""
    event = dict(result)
    event['type'] = 'claude-code-result'
    event['model'] = generation_model(result)
    return event

LIMIT_PATTERN = re.compile(r"hit your (session|usage|weekly|daily) limit|usage limit|rate limit|out of (extra )?usage|resets? (at|in) ", re.IGNORECASE)
RESET_PATTERN = re.compile(r"resets? (?:at )?(\d{1,2}(?::\d{2})?\s*[ap]m)(?:\s*\(([^)]+)\))?", re.IGNORECASE)

def usage_limit(event):
    """The limit message when the sign-in is usage-limited, else None. Never a model answer."""
    text = str(event.get('result') or '')
    if (event.get('is_error') or event.get('subtype') != 'success') and LIMIT_PATTERN.search(text):
        return text[:500]
    return None

def limit_reset_epoch(message, now=None):
    """Best-effort epoch seconds of the next reset named in a limit message; None if unparseable."""
    import datetime, zoneinfo
    match = RESET_PATTERN.search(message or '')
    if not match:
        return None
    clock, zone = match.group(1).replace(' ', '').lower(), match.group(2) or 'America/New_York'
    try:
        tz = zoneinfo.ZoneInfo(zone)
    except (KeyError, ValueError):
        tz = zoneinfo.ZoneInfo('America/New_York')
    fmt = '%I:%M%p' if ':' in clock else '%I%p'
    try:
        stamp = datetime.datetime.strptime(clock, fmt)
    except ValueError:
        return None
    current = datetime.datetime.fromtimestamp(now if now is not None else time.time(), tz)
    target = current.replace(hour=stamp.hour, minute=stamp.minute, second=0, microsecond=0)
    if target <= current:
        target += datetime.timedelta(days=1)
    return target.timestamp()

def gate_reset_epoch():
    """Reset time of a limit observed by any concurrent call; None when clear."""
    if not LIMIT_GATE.exists():
        return None
    try:
        until = json.loads(LIMIT_GATE.read_text()).get('resetsAtEpoch')
    except ValueError:
        return None
    return float(until) if until else None

def gate_wait_seconds(now=None, cleared=0.0):
    """Seconds until the published limit resets; 0 when clear or already waited out."""
    until = gate_reset_epoch()
    now = now if now is not None else time.time()
    return max(0.0, until-now) if until and until > cleared else 0.0

def record_gate(message, now=None):
    """Publish the observed limit so concurrent workers pause instead of burning requests."""
    now = now if now is not None else time.time()
    reset = limit_reset_epoch(message, now) or now+UNKNOWN_RESET_WAIT_SECONDS
    LIMIT_GATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = LIMIT_GATE.with_suffix('.tmp.'+str(os.getpid()))
    temporary.write_text(json.dumps({'observedAt': now, 'message': message, 'resetsAtEpoch': reset}))
    temporary.replace(LIMIT_GATE)
    return reset

def output_from(result, directory=None):
    """(parsed JSON output, usage, status) from a transport result of this provider."""
    events = result.get('events', [])
    if not events:
        return None, {}, 'usage_limited' if result.get('usageLimit') else 'transport_failed'
    event = events[-1]
    usage = event.get('usage') or {}
    if usage_limit(event):
        return None, usage, 'usage_limited'
    if event.get('model') != MODEL:
        return None, usage, 'model_mismatch'
    if event.get('stop_reason') == 'refusal':
        return None, usage, 'refusal'
    if event.get('is_error') or event.get('subtype') != 'success':
        return None, usage, str(event.get('subtype') or 'error')
    output = event.get('structured_output')
    if output is None:
        raw = event.get('result') or ''
        if not raw and directory is not None and (Path(directory)/'output.txt').exists():
            raw = (Path(directory)/'output.txt').read_text()
        try:
            output = json.loads(raw)
        except ValueError:
            return None, usage, 'invalid_json'
    return output, usage, 'completed'

def run(job, output_dir, runner=None, sleeper=time.sleep, clock=time.time):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    request = build_request(job)
    payload = json.dumps(request, ensure_ascii=False).encode()
    (output_dir/'model-request.json').write_bytes(payload)
    started = clock()
    state = {'provider': PROVIDER, 'model': MODEL, 'requests': [], 'events': [], 'limitPolicy': LIMIT_POLICY,
             'requestedMaxOutputTokens': job.get('maxOutputTokens'), 'maxBudgetUsd': request['maxBudgetUsd']}
    def checkpoint():
        temporary = output_dir/'transport-checkpoint.json.tmp'
        temporary.write_text(json.dumps(state, indent=2))
        temporary.replace(output_dir/'transport-checkpoint.json')
    def pause(seconds, reason):
        seconds = min(seconds, max(0.0, MAX_LIMIT_WAIT_SECONDS-waited[0]))
        state.setdefault('limitWaits', []).append({'reason': reason, 'seconds': seconds, 'at': clock()})
        checkpoint()
        remaining = seconds
        while remaining > 0:
            step = min(60.0, remaining); sleeper(step); remaining -= step
        waited[0] += seconds
    waited, cleared = [0.0], [0.0]
    checkpoint()
    try:
        binary = executable()
        state['executable'] = binary
        for attempt in range(MAX_LIMIT_WAITS+1):
            gate = gate_wait_seconds(clock(), cleared[0])
            if gate > 0 and LIMIT_POLICY == 'wait':
                cleared[0] = gate_reset_epoch() or 0.0
                pause(gate+RESET_GRACE_SECONDS, 'shared-gate')
            record = {'requestSha256': hashlib.sha256(payload).hexdigest(), 'exitCode': None, 'status': None, 'attempt': attempt}
            state['requests'].append(record); checkpoint()
            with tempfile.TemporaryDirectory(prefix='mop-blind-client-') as cwd:
                # No repository context, settings, memory, MCP servers, tools or saved session.
                with (output_dir/'client-stderr.log').open('a') as stderr:
                    process = (runner or subprocess.Popen)([binary, *request['argv']], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                                           stderr=stderr, text=True, cwd=cwd, env=child_env())
                    (output_dir/'process.json').write_text(json.dumps({'pid': process.pid, 'startedAt': started, 'model': MODEL, 'attempt': attempt}))
                    try:
                        stdout, _ = process.communicate(request['input'], timeout=TIMEOUT_SECONDS)
                    except subprocess.TimeoutExpired:
                        process.kill(); stdout, _ = process.communicate()
                        state.setdefault('transportErrors', []).append('TimeoutExpired')
            record['exitCode'] = process.returncode
            with (output_dir/'client-output.json').open('a') as raw:
                raw.write((stdout or '')+'\n')
            try:
                result = json.loads(stdout)
            except ValueError:
                state.setdefault('transportErrors', []).append('UnparseableClientOutput')
                break
            event = event_from(result)
            state['events'].append(event)
            record['status'] = 'ok' if not event.get('is_error') and event.get('subtype') == 'success' else 'error'
            record['sessionId'] = event.get('session_id')
            state['stopReason'] = event.get('stop_reason'); state['subtype'] = event.get('subtype')
            state['costUsd'] = sum(e.get('total_cost_usd') or 0 for e in state['events'])
            if event.get('is_error') or event.get('subtype') != 'success':
                state.setdefault('serviceErrors', []).append(json.dumps({'subtype': event.get('subtype'), 'result': str(event.get('result'))[:2000],
                                                                          'apiErrorStatus': event.get('api_error_status'), 'attempt': attempt}))
            (output_dir/'output.txt').write_text(str(event.get('result') or ''))
            limited = usage_limit(event)
            if not limited:
                break
            reset = record_gate(limited, clock())
            state['usageLimit'] = {'message': limited, 'resetsAtEpoch': reset, 'attempt': attempt}
            if LIMIT_POLICY != 'wait' or attempt >= MAX_LIMIT_WAITS or waited[0] >= MAX_LIMIT_WAIT_SECONDS:
                break
            cleared[0] = reset
            pause(max(0.0, reset-clock())+RESET_GRACE_SECONDS, 'usage-limit')
    except RuntimeError as exc:
        state.setdefault('transportErrors', []).append(type(exc).__name__ + ': ' + str(exc))
    except OSError as exc:
        state.setdefault('transportErrors', []).append(type(exc).__name__ + ': ' + str(exc))
    finally:
        checkpoint()
    state['seconds'] = clock()-started
    (output_dir/'transport-result.json').write_text(json.dumps(state, indent=2))
    return state

def smoke_job():
    """A synthetic public-only job for verifying the sign-in and request shape. Not research data."""
    schema = {'type': 'object', 'properties': {'outcomeA': {'type': 'string'}, 'outcomeB': {'type': 'string'}, 'limitations': {'type': 'string'}},
              'required': ['outcomeA', 'outcomeB', 'limitations'], 'additionalProperties': False}
    market = {'marketId': 'smoke-0', 'question': 'Will the synthetic committee publish its report before the deadline?',
              'rules': 'Resolves to Yes if the committee publishes the report on or before the stated deadline; otherwise No.',
              'outcomeLabels': ['Yes', 'No']}
    return {'instructions': 'Restate each outcome of the supplied public market as one plain-English factual claim. Return only the JSON object. No tools are available.',
            'input': {'publicMarket': market, 'independentTrial': 1}, 'effort': 'low', 'schema': schema, 'maxBudgetUsd': 1.0}

if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke', action='store_true', help='use the synthetic smoke job instead of a job file')
    parser.add_argument('job', nargs='?', help='job JSON path'); parser.add_argument('output'); args = parser.parse_args()
    if args.smoke == (args.job is not None): parser.error('give exactly one of --smoke or a job path')
    result = run(smoke_job() if args.smoke else json.loads(Path(args.job).read_text()), args.output)
    print(json.dumps({'model': result['model'], 'exitCodes': [r['exitCode'] for r in result['requests']], 'stopReason': result.get('stopReason'), 'limitWaits': len(result.get('limitWaits', [])),
                      'subtype': result.get('subtype'), 'costUsd': result.get('costUsd'), 'seconds': round(result['seconds'], 2),
                      'errors': result.get('transportErrors', []) + result.get('serviceErrors', [])}))
