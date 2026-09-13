"""Score frozen baseline outputs only against separately adjudicated labels."""
import argparse
import collections
from pathlib import Path

import real_answerability_v1 as a

QWEN = a.q.ROOT/'methods/baseline/development-scores.private.json'
REGEX = a.q.r.ROOT/'methods/baseline/development-scores.private.json'
METHOD_HASHES = {
    str(QWEN): '0214673c5bae53986ff1f5985d3ea086540357478cf71475bdc28635eca1d9bb',
    str(REGEX): 'e3dca30517f91406af317395c4e4bff974c23e0269b3d097d6f1730f0090c7fc',
}
ALLOWED = {'A', 'B', 'NONBINARY', 'INSUFFICIENT', 'AMBIGUOUS'}


def verify_raw_hashes(audit):
    for row in audit['rows']:
        for name, digest in row.get('fileHashes', {}).items():
            path = a.ROOT/name
            if not path.resolve().is_relative_to(a.ROOT.resolve()) or a.q.r.digest(path) != digest:
                raise RuntimeError('Raw annotation artifact changed after audit')


def check_labels(labels, plan):
    expected = {s['caseId'] for s in plan['selected']}
    if len(labels) != len(expected) or {r['caseId'] for r in labels} != expected:
        raise RuntimeError('Every selected pair must have exactly one explicit disposition')
    for row in labels:
        if row['settlementOutcome'] not in ALLOWED or row['reviewStatus'] not in ['adjudicated', 'unresolved']:
            raise RuntimeError('Invalid label disposition')
        if row['reviewStatus'] == 'unresolved' and row['settlementOutcome'] in ['A', 'B', 'NONBINARY']:
            raise RuntimeError('Unresolved label cannot become an answerable case')
        if not row['reason'] or not row['reviewer'] or row.get('humanValidated') is not False:
            raise RuntimeError('This study requires a named model reviewer and explicit absence of human validation')
        job_path = a.ROOT/'jobs/a'/(row['caseId']+'.json')
        if row['jobSha256'] != a.q.r.digest(job_path):
            raise RuntimeError('Label input provenance mismatch')
        text = a.q.r.read(job_path)['input']['completeEmail']['completeSemanticText']
        quotes = row['supportingQuotes']
        if not isinstance(quotes, list) or any(not isinstance(s, str) or not s or s not in text for s in quotes):
            raise RuntimeError('Label contains a non-exact supporting quote')
        if row['settlementOutcome'] in ['A', 'B', 'NONBINARY'] and not quotes:
            raise RuntimeError('Answerable label lacks evidence')


def seal():
    plan = a.verify_plan()
    audit_path = a.ROOT/'raw-audit.private.json'
    audit = a.q.r.read(audit_path)
    if audit['partial'] or audit['accountedFor'] != len(plan['entries']) or audit['planSha256'] != a.q.r.digest(a.ROOT/'plan.private.json'):
        raise RuntimeError('Complete raw audit required before label sealing')
    verify_raw_hashes(audit)
    labels_path = a.ROOT/'adjudicated-labels.private.json'
    labels = a.q.r.read(labels_path)
    check_labels(labels, plan)
    for file, digest in METHOD_HASHES.items():
        if a.q.r.digest(file) != digest:
            raise RuntimeError('Frozen baseline scores changed')
    a.write_once(a.ROOT/'adjudicated-labels-seal.json', {
        'at': a.q.r.now(), 'labelsSha256': a.q.r.digest(labels_path),
        'planSha256': a.q.r.digest(a.ROOT/'plan.private.json'),
        'rawAuditSha256': a.q.r.digest(audit_path), 'scorerSha256': a.q.r.digest(Path(__file__)),
        'methodHashes': METHOD_HASHES, 'humanValidated': False,
        'qualification': 'Model-adjudicated exposed development panel; not a validated deployment projection.'})


def regex_decision(row):
    score = row.get('factualScore') or {}
    if row.get('status') != 'completed' or not score.get('validPair') or score.get('status') not in ['hit', 'miss', 'wrong-outcome', 'conflict']:
        return 'UNSCORABLE'
    matches = score['matches']
    mask = [m is not None for m in matches]
    return {(True, False): 'A', (False, True): 'B', (False, False): 'NEITHER', (True, True): 'CONFLICT'}[tuple(mask)]


def measure(labels, decisions):
    if set(decisions) != {r['caseId'] for r in labels} or any(v not in ['A', 'B', 'NEITHER', 'CONFLICT', 'UNSCORABLE'] for v in decisions.values()):
        raise ValueError('Missing case or invalid decision')
    answerable = [r for r in labels if r['reviewStatus'] == 'adjudicated' and r['settlementOutcome'] in ['A', 'B']]
    categories = collections.Counter()
    for row in answerable:
        predicted = decisions[row['caseId']]
        categories['correct' if predicted == row['settlementOutcome'] else
                   'wrongSide' if predicted in ['A', 'B'] else
                   'conflict' if predicted == 'CONFLICT' else
                   'executionFailure' if predicted == 'UNSCORABLE' else 'abstention'] += 1
    insufficient = [r for r in labels if r['reviewStatus'] == 'adjudicated' and r['settlementOutcome'] == 'INSUFFICIENT']
    unsupported = sum(decisions[r['caseId']] in ['A', 'B', 'CONFLICT'] for r in insufficient)
    attempted = categories['correct'] + categories['wrongSide']
    return {'panelPairs': len(labels), 'executionFailuresAcrossPanel': sum(v == 'UNSCORABLE' for v in decisions.values()),
            'answerablePairs': len(answerable), **{k: categories[k] for k in ['correct', 'wrongSide', 'conflict', 'executionFailure', 'abstention']},
            'recoveryAmongAnswerable': categories['correct']/len(answerable) if answerable else None,
            'correctnessAmongDirectionalAnswersOnAnswerablePairs': categories['correct']/attempted if attempted else None,
            'reviewedInsufficientPairs': len(insufficient), 'directionalOrConflictingOutputsOnInsufficientPairs': unsupported,
            'nonbinaryPairs': sum(r['reviewStatus'] == 'adjudicated' and r['settlementOutcome'] == 'NONBINARY' for r in labels),
            'unresolvedPairs': sum(r['reviewStatus'] != 'adjudicated' or r['settlementOutcome'] == 'AMBIGUOUS' for r in labels)}


def score():
    plan = a.verify_plan()
    seal_path = a.ROOT/'adjudicated-labels-seal.json'
    sealed = a.q.r.read(seal_path)
    paths = {'labelsSha256': a.ROOT/'adjudicated-labels.private.json',
             'planSha256': a.ROOT/'plan.private.json', 'rawAuditSha256': a.ROOT/'raw-audit.private.json',
             'scorerSha256': Path(__file__)}
    for field, path in paths.items():
        if a.q.r.digest(path) != sealed[field]:
            raise RuntimeError('Sealed scoring dependency changed')
    labels = a.q.r.read(paths['labelsSha256'])
    check_labels(labels, plan)
    verify_raw_hashes(a.q.r.read(paths['rawAuditSha256']))
    if sealed['methodHashes'] != METHOD_HASHES:
        raise RuntimeError('Baseline cohort changed')
    for path, digest in METHOD_HASHES.items():
        if a.q.r.digest(path) != digest:
            raise RuntimeError('Baseline score source changed')
    # Method outputs are loaded only after the label seal has passed all gates.
    qr = {r['caseId']: r for r in a.q.r.read(QWEN) if r['kind'] == 'factual'}
    rr = {r['marketId']: r for r in a.q.r.read(REGEX) if r.get('factualScore') is not None}
    regex = {s['caseId']: regex_decision(rr[s['marketId']]) for s in plan['selected']}
    strict = {s['caseId']: qr[s['caseId']]['settlementOutcome'] for s in plan['selected']}
    quoted = {cid: side if qr[cid]['exactQuote'] or side not in ['A', 'B'] else 'NEITHER' for cid, side in strict.items()}
    selected = {s['caseId']: s for s in plan['selected']}
    answerable_ids = [r['caseId'] for r in labels if r['reviewStatus'] == 'adjudicated' and r['settlementOutcome'] in ['A', 'B']]
    result = {'at': a.q.r.now(), 'labelSealSha256': a.q.r.digest(seal_path),
              'panelPairs': len(labels), 'answerableDistinctEmails': len({selected[c]['emailId'] for c in answerable_ids}),
              'answerableDistinctFamilies': len({selected[c]['family'] for c in answerable_ids}),
              'labelDispositions': dict(collections.Counter((r['reviewStatus'] + ':' + r['settlementOutcome']) for r in labels)),
              'regexCandidateSide': measure(labels, regex), 'qwenStrictSide': measure(labels, strict),
              'qwenStrictSideWithExactQuote': measure(labels, quoted),
              'qualification': 'Conditional on model-adjudicated labels, not independent human gold. Regex is a directional detector, not a full source/time verifier. No contract execution, on-chain acceptance or real-world market coverage is measured.'}
    a.write_once(a.ROOT/'adjudicated-baseline-comparison.private.json', result)
    print(a.q.r.read(a.ROOT/'adjudicated-baseline-comparison.private.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['seal', 'score'])
    args = parser.parse_args()
    {'seal': seal, 'score': score}[args.command]()
