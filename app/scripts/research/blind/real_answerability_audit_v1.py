"""Independent raw-artifact gate for the frozen answerability annotations."""
import argparse
import collections
import hashlib
import json
from pathlib import Path

import real_answerability_v1 as a


def reconcile(entry):
    root = a.ROOT
    directory = root/'responses'/entry['name']
    job = a.q.r.read(root/'jobs'/(entry['name']+'.json'))
    saved = a.q.r.read(directory/'review.private.json')
    if (saved.get('name'), saved.get('caseId'), saved.get('pass')) != (entry['name'], entry['caseId'], entry['pass']):
        raise RuntimeError('Annotation identity mismatch')
    if saved['status'] not in ['completed', 'invalid_annotation']:
        return {'name': entry['name'], 'status': saved['status'], 'rawVerified': False,
                'qualification': 'Failed annotation is retained and cannot supply an accepted label'}
    actual_job, effective = a.q.verify_teacher(directory)
    if actual_job != job or effective['selectedAttempt'] != 0 or len(effective['attempts']) != 1:
        raise RuntimeError('Unexpected input or extra teacher attempt')
    transport = a.q.r.read(directory/'transport-result.json')
    request_bytes = (directory/'model-request.json').read_bytes()
    requests = transport.get('requests', [])
    if len(requests) != 1 or requests[0]['status'] != 200 or requests[0]['requestSha256'] != hashlib.sha256(request_bytes).hexdigest():
        raise RuntimeError('Actual upstream request count/status/hash differs')
    terminal = transport.get('events', [])
    if len(terminal) != 1 or terminal[0]['type'] != 'response.completed':
        raise RuntimeError('Missing unique completed service event')
    response = terminal[0]['response']
    if response.get('model') != 'gpt-6-astra' or response.get('status') != 'completed':
        raise RuntimeError('Model or service status mismatch')
    # Require a service message, not an unbound client output.txt fallback.
    items = response.get('output') or transport.get('outputItems', [])
    text = ''.join(c.get('text', '') for i in items if i.get('type') == 'message'
                   for c in i.get('content', []) if c.get('type') == 'output_text')
    if not text:
        raise RuntimeError('No raw service output text')
    raw = json.loads(text)
    if raw != effective['output'] or raw != saved['output']:
        raise RuntimeError('Saved annotation differs from raw service output')
    errors = a.validate_output(raw, job)
    expected_status = 'invalid_annotation' if errors else 'completed'
    if errors != saved['validationErrors'] or saved['status'] != expected_status:
        raise RuntimeError('Annotation validation was not reproduced')
    request = json.loads(request_bytes)
    if request['tools'] != [] or request['tool_choice'] != 'none' or request['reasoning']['effort'] != 'high':
        raise RuntimeError('Tool or reasoning configuration differs')
    usage = response.get('usage', {})
    return {'name': entry['name'], 'status': saved['status'], 'rawVerified': True,
            'validationErrors': errors, 'inputTokens': usage.get('input_tokens'),
            'outputTokens': usage.get('output_tokens'), 'usage': usage,
            'seconds': transport.get('seconds'),
            'fileHashes': {str(p.relative_to(root)): a.q.r.digest(p)
                           for p in directory.iterdir() if p.is_file()}}


def audit(partial=False):
    plan = a.verify_plan()
    finished = a.ROOT/'run-finished.json'
    if not partial and not finished.exists():
        raise RuntimeError('Full audit requires a finished runner')
    rows, pending = [], []
    for entry in plan['entries']:
        if not (a.ROOT/'responses'/entry['name']/'review.private.json').exists():
            pending.append(entry['name'])
        else:
            rows.append(reconcile(entry))
    if pending and not partial:
        raise RuntimeError('Full audit requires accounting for every planned review')
    result = {'at': a.q.r.now(), 'planSha256': a.q.r.digest(a.ROOT/'plan.private.json'),
              'auditorSha256': a.q.r.digest(Path(__file__)),
              'partial': bool(pending) or not finished.exists(), 'planned': len(plan['entries']),
              'accountedFor': len(rows), 'rawVerified': sum(r['rawVerified'] for r in rows),
              'statuses': dict(collections.Counter(r['status'] for r in rows)),
              'knownInputTokens': sum(r.get('inputTokens') or 0 for r in rows),
              'knownOutputTokens': sum(r.get('outputTokens') or 0 for r in rows),
              'missingUsageRecords': sum(r.get('inputTokens') is None or r.get('outputTokens') is None for r in rows),
              'pending': pending, 'rows': rows,
              'adjudicatedLabels': False,
              'qualification': 'Raw request/output integrity only. Human-independent label correctness and settlement accuracy are not established.'}
    if partial:
        a.q.r.save(a.ROOT/'raw-audit-progress.private.json', result)
    else:
        a.write_once(a.ROOT/'raw-audit.private.json', result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['pending', 'rows']}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--partial', action='store_true')
    args = parser.parse_args()
    audit(args.partial)
