"""Prepare and seal a diagnostic from already-open development cases only."""
import argparse
import collections
import copy
import json
import subprocess
import sys
import probe as p

ORDER = p.ROOT.parent / 'qwen-order-probe-20260913'


def prepare():
    o = p.o
    o.require(not (p.ROOT / 'input-freeze.json').exists(), 'Already frozen')
    old = o.read(ORDER / 'panel.private.json')
    cases = copy.deepcopy(old['cases'])
    o.require(len(cases) == len({x['item']['caseId'] for x in cases}) == 12, 'Panel differs')
    for entry in cases:
        entry['executionOrder'] = ['basis-first' if x == 'quote-first' else x for x in entry['executionOrder']]
    o.require(collections.Counter(x['executionOrder'][0] for x in cases) == {'original': 6, 'basis-first': 6}, 'Order unbalanced')
    o.once(p.ROOT / 'panel.private.json', {'at': o.now(), 'cases': cases, 'selectionSourceHashes': old['selectionSourceHashes'],
        'sourcePanelSha256': o.digest(ORDER / 'panel.private.json'), 'noNewSelectionFromV3': True})
    requests = []
    for entry in cases:
        for variant in p.VARIANTS:
            request = p.request_for(entry['baselineRequest'], variant)
            directory = p.ROOT / 'calls' / entry['item']['caseId'] / variant
            o.once(directory / 'request.json', request)
            wire = directory / 'request-wire.json'
            with wire.open('xb') as handle: handle.write(o.wire(request))
            wire.chmod(0o600)
            requests.append({'caseId': entry['item']['caseId'] + '/' + variant, 'request': request})
    o.once(p.ROOT / 'requests.private.json', {'identifier': o.read(p.ROOT / 'runtime.json')['identifier'], 'requests': requests})
    o.once(p.ROOT / 'protocol.json', {'createdAt': o.now(), 'hypothesis': 'Explicit compact entity/value/comparison before classification may reduce semantic inversions that an exact quote alone did not correct.',
        'panel': 'Same12olddevelopmentcases as order and predicate probes;6positive4negativecontrols2natural factual candidates. Three baseball controls share an event. Reused selected diagnostic panel, not independent evaluation.',
        'procedure': 'Fresh paired original baseline replay and basis-first intervention; full unchanged baseline rule and email. Only system appendix and added decisionBasis schema change. Original five output fields keep their meaning and are scored without correcting verdicts from the basis.',
        'appendix': p.APPENDIX, 'basisSchema': p.BASIS_SCHEMA,
        'runtime': 'Same pinned Qwen artifact, context, temperature0,seed20260912,max2048outputtokens.24calls,4concurrentpairs,withinpairserial,6originalfirst6basisfirst. Full preflight and server inputtoken reconciliation required.',
        'executionGate': 'Freeze before any V3 local outcomes; execute only after V3 completion and explicit local-inference quiescence. No reserved contents read. No automatic retry, truncation, adoption or benchmark replacement.',
        'reporting': 'Full and common-completed counts; original replay variation; exact basis quote separately from unchanged final evidenceQuote score; actual nested field order; independent known input/output/duration totals and missingness. Manually assess all12basis outputs. Latency observational.',
        'adoption': 'Any useful result requires a new named full-cohort method with per-method request/schema/scoring lineage and reserved-evaluator adapter review before selection. Neither derived calculation nor quoted basis is a cryptographic proof.'})
    print('Prepared24frozen-input requests without model calls; run tests, freeze, and request independent code review.')


def freeze():
    o = p.o
    o.require(not (o.STUDY / 'methods/v3/development-judgments.private.json').exists(), 'V3 outcomes already available')
    o.require(not list((o.STUDY / 'methods/v3/development').glob('*/*/started.json')), 'V3 inference already began; cannot claim pre-outcome freeze')
    test = subprocess.run([sys.executable, '-m', 'unittest', '-v', 'test_probe.py'], capture_output=True, text=True)
    o.once(p.ROOT / 'test-result.json', {'at': o.now(), 'returncode': test.returncode, 'stdout': test.stdout, 'stderr': test.stderr})
    o.require(test.returncode == 0, 'Tests failed')
    external = copy.deepcopy(o.read(ORDER / 'input-freeze.json')['externalFileHashes'])
    for name in ['panel.private.json', 'summary.private.json', 'input-freeze.json']:
        external[str(ORDER / name)] = o.digest(ORDER / name)
    external[str(ORDER / 'probe.py')] = o.digest(ORDER / 'probe.py')
    for name, expected in external.items(): o.require(o.digest(name) == expected, 'External source changed: ' + name)
    files = {str(path.relative_to(p.ROOT)): o.digest(path) for path in p.ROOT.rglob('*') if path.is_file() and '__pycache__' not in path.parts}
    o.once(p.ROOT / 'input-freeze.json', {'frozenAt': o.now(), 'fileHashes': files, 'externalFileHashes': external,
        'pythonVersion': sys.version, 'newModelCalls': 0, 'reservedInputsRead': False, 'beforeV3LocalInference': True})
    for path in p.ROOT.rglob('*'):
        path.chmod(0o700 if path.is_dir() else 0o600)
    print(json.dumps({'inputFreezeSha256': o.digest(p.ROOT / 'input-freeze.json'), 'files': len(files), 'testsPassed': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('phase', choices=['prepare', 'freeze'])
    args = parser.parse_args(); {'prepare': prepare, 'freeze': freeze}[args.phase]()
