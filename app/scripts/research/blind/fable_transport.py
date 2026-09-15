"""A single isolated Claude Fable 5.1 response through the official Anthropic SDK.

This is the live blind generator transport. It replaces the Codex/Astra
loopback adapter (``astra_transport.py``) for every new rule draw, prompt
optimization and teacher call. The Astra module stays in place, unchanged, so
frozen experiment artifacts can still be reconciled against their original
request shape.

Invariants shared with the Astra transport:

* The request is built only from an explicit, audited job (instructions,
  public input, JSON schema, effort). Nothing from the coordinator's process,
  repository, conversation history or private evidence reaches the model.
* No tools, no tool choice, no sampling parameters, no assistant prefill.
  Thinking is always on for this model; the transport does not configure it.
* The exact request body is written to ``model-request.json`` without any
  authentication material, and its SHA-256 is recorded with the HTTP status.
* Raw completion output and token accounting are retained. Failures are
  retained as receipts; the transport never retries on its own.
* No server-side model fallback is configured. A refusal is recorded as a
  terminal ``refusal`` status rather than silently served by another model,
  so the generator identity of every artifact stays ``claude-fable-5-1``.

Credentials: ``ANTHROPIC_API_KEY`` in the environment, else ``apiKey`` in
``~/.config/means-of-prediction/anthropic.json`` (mode 0600). Neither value is
ever written into an artifact.
"""
import argparse, hashlib, json, os, time
from pathlib import Path

MODEL = 'claude-fable-5-1'
PROVIDER = 'anthropic'
DEFAULT_MAX_OUTPUT_TOKENS = 64000
EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')
CREDENTIAL_FILE = Path.home()/'.config/means-of-prediction/anthropic.json'
TIMEOUT_SECONDS = 600.0

def build_request(job):
    """Exact Messages API body for one blind job. Contains no auth material."""
    effort = job.get('effort', 'high')
    if effort not in EFFORTS:
        raise ValueError('Unsupported effort for ' + MODEL + ': ' + str(effort))
    body = {
        'model': MODEL,
        'max_tokens': job['maxOutputTokens'] if job.get('maxOutputTokens') is not None else DEFAULT_MAX_OUTPUT_TOKENS,
        'system': job['instructions'],
        'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': json.dumps(job['input'], ensure_ascii=False)}]}],
        'output_config': {'effort': effort, 'format': {'type': 'json_schema', 'schema': job['schema']}},
    }
    # Inherited job keys such as tools/messages/temperature are dropped by construction.
    return body

def api_key():
    """Resolve the API key without ever placing it in a job or artifact."""
    key = os.environ.get('ANTHROPIC_API_KEY')
    if key:
        return key
    if CREDENTIAL_FILE.exists():
        key = json.loads(CREDENTIAL_FILE.read_text()).get('apiKey')
        if key:
            return key
    raise RuntimeError('No Anthropic credential: set ANTHROPIC_API_KEY or write {"apiKey": ...} to ' + str(CREDENTIAL_FILE))

def make_client():
    import anthropic
    # max_retries=0: every attempt is a recorded request; recovery is a coordinator decision.
    return anthropic.Anthropic(api_key=api_key(), max_retries=0, timeout=TIMEOUT_SECONDS)

def output_from(result, directory=None):
    """(parsed JSON output, usage, status) from a transport result of this provider."""
    events = result.get('events', [])
    if not events:
        return None, {}, 'transport_failed'
    message = events[-1]
    usage = message.get('usage', {})
    if message.get('model') != MODEL:
        return None, usage, 'model_mismatch'
    stop = message.get('stop_reason')
    status = {'end_turn': 'completed', 'max_tokens': 'incomplete', 'refusal': 'refusal'}.get(stop, stop or 'unknown')
    if status != 'completed':
        return None, usage, status
    raw = ''.join(block.get('text', '') for block in message.get('content', []) if block.get('type') == 'text')
    if not raw and directory is not None:
        path = Path(directory)/'output.txt'
        if path.exists():
            raw = path.read_text()
    try:
        return json.loads(raw), usage, status
    except ValueError:
        return None, usage, 'invalid_json'

def run(job, output_dir, client=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    body = build_request(job)
    payload = json.dumps(body, ensure_ascii=False).encode()
    (output_dir/'model-request.json').write_bytes(payload)
    started = time.time()
    state = {'provider': PROVIDER, 'model': MODEL, 'requests': [], 'events': [],
             'requestedMaxOutputTokens': job.get('maxOutputTokens'), 'effectiveMaxTokens': body['max_tokens']}
    (output_dir/'process.json').write_text(json.dumps({'pid': os.getpid(), 'startedAt': started, 'model': MODEL}))
    def checkpoint():
        temporary = output_dir/'transport-checkpoint.json.tmp'
        temporary.write_text(json.dumps(state, indent=2))
        temporary.replace(output_dir/'transport-checkpoint.json')
    request = {'requestSha256': hashlib.sha256(payload).hexdigest(), 'status': None}
    state['requests'].append(request)
    checkpoint()
    import anthropic
    try:
        client = client or make_client()
        # Streaming keeps minutes-long generations alive; the full message is assembled locally.
        with client.messages.stream(**body) as stream:
            message = stream.get_final_message()
        request['status'] = 200
        request['requestId'] = getattr(message, '_request_id', None)
        record = message.to_dict()
        record['type'] = 'message'
        # Thinking blocks carry no returned text on this model; retain only their presence.
        record['content'] = [block if block.get('type') != 'thinking' else {'type': 'thinking'} for block in record.get('content', [])]
        state['events'].append(record)
        state['stopReason'] = record.get('stop_reason')
        if record.get('stop_details') is not None:
            state['stopDetails'] = record['stop_details']
        text = ''.join(block.get('text', '') for block in record['content'] if block.get('type') == 'text')
        (output_dir/'output.txt').write_text(text)
    except anthropic.APIStatusError as exc:
        request['status'] = exc.status_code
        request['requestId'] = getattr(exc, 'request_id', None)
        body_text = exc.response.text if getattr(exc, 'response', None) is not None else str(exc)
        state.setdefault('serviceErrors', []).append(body_text[:2000])
    except anthropic.APIConnectionError as exc:
        state.setdefault('transportErrors', []).append(type(exc).__name__)
    except RuntimeError as exc:
        # Missing credential: recorded as a receipt, never as a model response.
        state.setdefault('transportErrors', []).append(type(exc).__name__ + ': ' + str(exc))
    finally:
        checkpoint()
    state['seconds'] = time.time()-started
    (output_dir/'transport-result.json').write_text(json.dumps(state, indent=2))
    return state

def smoke_job():
    """A synthetic public-only job for verifying credentials and request shape. Not research data."""
    schema = {'type': 'object', 'properties': {'outcomeA': {'type': 'string'}, 'outcomeB': {'type': 'string'}, 'limitations': {'type': 'string'}},
              'required': ['outcomeA', 'outcomeB', 'limitations'], 'additionalProperties': False}
    market = {'marketId': 'smoke-0', 'question': 'Will the synthetic committee publish its report before the deadline?',
              'rules': 'Resolves to Yes if the committee publishes the report on or before the stated deadline; otherwise No.',
              'outcomeLabels': ['Yes', 'No']}
    return {'instructions': 'Restate each outcome of the supplied public market as one plain-English factual claim. Return only the JSON object.',
            'input': {'publicMarket': market, 'independentTrial': 1}, 'effort': 'low', 'schema': schema, 'maxOutputTokens': 2000}

if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke', action='store_true', help='use the synthetic smoke job instead of a job file')
    parser.add_argument('job', nargs='?', help='job JSON path'); parser.add_argument('output'); args = parser.parse_args()
    if args.smoke == (args.job is not None): parser.error('give exactly one of --smoke or a job path')
    result = run(smoke_job() if args.smoke else json.loads(Path(args.job).read_text()), args.output)
    print(json.dumps({'model': result['model'], 'httpStatuses': [r['status'] for r in result['requests']],
                      'stopReason': result.get('stopReason'), 'seconds': round(result['seconds'], 2)}))
