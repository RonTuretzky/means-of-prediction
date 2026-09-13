"""Declared teacher-only recovery; no local inference or scored resampling."""
import json
import os
from pathlib import Path
import qwen_round1 as q

POLICY = 'v2-teacher-capacity-recovery-policy.json'
STOP = 'v2-teacher-capacity-stop.json'


def usage_limited(directory):
    path = Path(directory) / 'transport-result.json'
    if not path.exists():
        return False
    for error in q.r.read(path).get('serviceErrors', []):
        try:
            value = json.loads(error) if isinstance(error, str) else error
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and isinstance(value.get('error'), dict) and value['error'].get('type') == 'usage_limit_reached':
            return True
    return False


def teacher(job, directory):
    directory = Path(directory)
    if (directory / 'teacher-effective.json').exists():
        original, effective = q.verify_teacher(directory)
        if original != job:
            raise RuntimeError('Existing teacher input differs')
        return effective
    policy = q.load(POLICY)
    relative = str(directory.relative_to(q.ROOT))
    prior = policy['priorFailedRequests'].get(relative)
    if prior and prior['sameInputSha256'] != q.r.hash_value(job):
        raise RuntimeError('Declared teacher input differs')
    count = prior['failedAttempts'] if prior else 0
    if not prior and (directory / 'parsed.json').exists():
        raise RuntimeError('Undeclared existing failed teacher attempt')
    attempts = []
    for number in range(count):
        d = directory if number == 0 else directory / 'teacher-recovery' / str(number)
        parsed = q.r.read(d / 'parsed.json')
        q.r.verify_model_artifact(d, job, parsed)
        if parsed['status'] == 'completed':
            raise RuntimeError('Declared failed teacher was completed')
        attempts.append({'directory': str(d), 'status': parsed['status'], 'parsedSha256': q.r.digest(d / 'parsed.json')})
    if (q.ROOT / STOP).exists():
        raise RuntimeError('Fresh hosted usage limit reached; no further calls')
    d = directory if count == 0 else directory / 'teacher-recovery' / str(count)
    if (d / 'model-request.json').exists() or (d / 'parsed.json').exists():
        raise RuntimeError('Recovery attempt already started; reconcile without retry')
    try:
        parsed = q.r.safe_call(job, d)
    except RuntimeError:
        if not (d / 'parsed.json').exists():
            raise
        parsed = q.r.read(d / 'parsed.json')
    if usage_limited(d):
        q.once(STOP, {'at': q.r.now(), 'directory': str(d), 'parsedSha256': q.r.digest(d / 'parsed.json'),
                      'policySha256': q.r.digest(q.ROOT / POLICY), 'reason': 'Fresh usage_limit_reached; no more hosted calls.'})
        raise RuntimeError('Fresh usage_limit_reached; hosted recovery stopped')
    if parsed['status'] != 'completed' or not isinstance(parsed.get('output'), dict):
        raise RuntimeError('Single declared teacher attempt failed; retained without retry')
    attempts.append({'directory': str(d), 'status': parsed['status'], 'parsedSha256': q.r.digest(d / 'parsed.json')})
    effective = {'selectedAttempt': count, 'attempts': attempts, 'sameInputSha256': q.r.hash_value(job),
                 'output': parsed['output'], 'status': 'completed'}
    q.r.save(directory / 'teacher-effective.json', effective)
    return effective


def main():
    os.umask(0o077)
    policy = q.load(POLICY)
    if q.load('driver/v2/feedback/completed.json')['returncode'] != 1:
        raise RuntimeError('Expected preserved feedback failure')
    try:
        os.kill(policy['exitedFeedbackPid'], 0)
    except ProcessLookupError:
        pass
    else:
        raise RuntimeError('Previous feedback owner is still alive')
    for name, digest in policy['preservedFileHashes'].items():
        if q.r.digest(q.ROOT / name) != digest:
            raise RuntimeError('Prior teacher artifact changed: ' + name)
    for name, digest in policy['sourceHashes'].items():
        if q.r.digest(Path(__file__).parent / name) != digest:
            raise RuntimeError('Recovery source changed: ' + name)
    q.teacher_call = teacher
    # Serial dispatch ensures no new call follows the first fresh usage error.
    q.distill('v2', workers=1, stream=True)
    q.audit()
    q.report()


if __name__ == '__main__':
    main()
