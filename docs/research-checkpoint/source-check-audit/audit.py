"""CPU-only independent raw/score/replay reconciliation after the root audit."""
import collections
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, '/Users/wk/conductor/workspaces/research/porto-novo/app/scripts/research/blind')
import qwen_source_check_v1 as s

HERE = Path(__file__).resolve().parent
PLAN_SHA = '0eef2547435c8ef2b2a27307c19cc215ad440661002f39345fb3821db9303c5f'


def strict(output):
    a, b = output['outcomeA'] == 'YES', output['outcomeB'] == 'YES'
    return 'CONFLICT' if a and b else 'A' if a else 'B' if b else 'NEITHER'


def measure(labels, decisions):
    assert len(labels) == len(decisions) and {x['caseId'] for x in labels} == set(decisions)
    assert all(x in ['A', 'B', 'NEITHER', 'CONFLICT', 'UNSCORABLE'] for x in decisions.values())
    eligible = [x for x in labels if x['reviewStatus'] == 'adjudicated' and x['settlementOutcome'] in ['A', 'B']]
    insufficient = [x for x in labels if x['reviewStatus'] == 'adjudicated' and x['settlementOutcome'] == 'INSUFFICIENT']
    names = {'NEITHER':'abstention', 'CONFLICT':'conflict', 'UNSCORABLE':'executionFailure'}
    counts = collections.Counter()
    for x in eligible:
        d = decisions[x['caseId']]
        counts[('correct' if d == x['settlementOutcome'] else 'wrongSide') if d in ['A', 'B'] else names[d]] += 1
    directions = counts['correct'] + counts['wrongSide']
    return {'panelPairs':len(labels), 'executionFailuresAcrossPanel':sum(x == 'UNSCORABLE' for x in decisions.values()),
        'answerablePairs':len(eligible), **{k:counts[k] for k in ['correct','wrongSide','conflict','executionFailure','abstention']},
        'recoveryAmongAnswerable':counts['correct']/len(eligible) if eligible else None,
        'correctnessAmongDirectionalAnswersOnAnswerablePairs':counts['correct']/directions if directions else None,
        'reviewedInsufficientPairs':len(insufficient),
        'directionalOrConflictingOutputsOnInsufficientPairs':sum(decisions[x['caseId']] in ['A','B','CONFLICT'] for x in insufficient),
        'nonbinaryPairs':sum(x['reviewStatus']=='adjudicated' and x['settlementOutcome']=='NONBINARY' for x in labels),
        'unresolvedPairs':sum(x['reviewStatus']!='adjudicated' or x['settlementOutcome']=='AMBIGUOUS' for x in labels)}


def known(values):
    valid = [x for x in values if type(x) in [float,int] and math.isfinite(x) and x >= 0]
    return {'knownTotal':sum(valid), 'missingOrInvalid':len(values)-len(valid), 'isLowerBound':len(valid)!=len(values)}


def main():
    assert s.q.r.digest(s.plan_path()) == PLAN_SHA
    plan = s.verify(); s.review_gate(plan)
    root_report_path = s.ROOT/'audited-results.private.json'
    report = s.q.r.read(root_report_path)
    assert report['planSha256'] == PLAN_SHA
    s.c.dead([s.q.r.read(s.ROOT/'started.json')['pid']])
    for name, sha in report['artifactHashes'].items():
        assert s.q.r.digest(s.ROOT/name) == sha
    expected_entries = {x['name']:x for x in plan['entries']}
    assert len(expected_entries) == len(plan['entries']) == 120
    reported = {x['name']:x for x in report['rows']}
    assert len(reported) == len(report['rows']) == 120 and set(reported) == set(expected_entries)
    wanted_calls = {k for k,e in expected_entries.items() if e['request'] is not None}
    actual_starts = {str(p.parent.relative_to(s.ROOT/'responses')) for p in (s.ROOT/'responses').rglob('started.json')}
    assert wanted_calls == actual_starts and len(actual_starts) == 110
    preflight = s.q.r.read(s.ROOT/'preflight.private.json')
    counts = {x['caseId']:x['inputTokens'] for x in preflight['sdk']['counts']}
    assert set(counts) == wanted_calls and len(counts) == len(preflight['sdk']['counts'])
    runtime = s.q.load('runtime.json')
    for phase in ['pre-launch','post-dispatch']:
        snapshot = s.q.r.read(s.ROOT/(phase+'.private.json'))
        s.c.validate_runtime(snapshot,runtime,preflight['sdk']['loadConfig'])
        assert snapshot['supplement'] == preflight['supplement']
    decisions = {v:{} for v in s.VARIANTS}; quoted = {v:{} for v in s.VARIANTS}
    outputs = {}; accounting = {v:[] for v in s.VARIANTS}; row_hashes = {}
    for name,e in expected_entries.items():
        directory = s.ROOT/'responses'/name
        if e['request'] is None:
            assert not directory.exists()
            status = 'rule_unavailable'; d = 'UNSCORABLE'; exact = False; usage = None; seconds = None; output = None
        else:
            request = s.q.r.read(directory/'request.json')
            assert request == e['request']
            result = s.q.r.read(directory/'result.json')
            assert result['requestSha256'] == s.q.r.hash_value(request)
            raw_path = directory/'response.raw'
            raw = None
            if raw_path.exists():
                assert result['rawResponseSha256'] == s.q.r.digest(raw_path)
                try: raw = json.loads(raw_path.read_bytes())
                except (ValueError,UnicodeDecodeError): pass
            if not isinstance(raw,dict):
                assert result['status'] == 'transport_failed' and result.get('output') is None
                output = None; usage = None; status = result['status']
            else:
                assert raw == s.q.r.read(directory/'response.json')
                assert result['responseSha256'] == s.q.r.digest(directory/'response.json')
                choice = (raw.get('choices') or [{}])[0]; message = choice.get('message',{})
                try: output = json.loads(message.get('content',''))
                except (ValueError,TypeError): output = None
                status = 'completed' if result.get('httpStatus')==200 and choice.get('finish_reason')=='stop' and s.q.valid_judgment(output) else 'failed'
                assert result['status']==status and result['output']==output
                assert result.get('returnedModel')==raw.get('model')
                if status=='completed' or raw.get('model') is not None: assert raw.get('model')==request['model']
                assert result.get('reasoningCharacters')==len(message.get('reasoning_content','') or '')
                assert result.get('finishReason')==choice.get('finish_reason')
                usage = raw.get('usage'); assert result.get('usage')==usage
            if usage is not None: assert usage.get('prompt_tokens')==counts[name]
            d = strict(output) if status=='completed' else 'UNSCORABLE'
            body = json.loads(request['messages'][1]['content'])['email']['completeSemanticText']
            exact = bool(isinstance(output,dict) and isinstance(output.get('evidenceQuote'),str) and output['evidenceQuote'] and output['evidenceQuote'] in body)
            seconds = result.get('seconds')
            accounting[e['variant']].append({'usage':usage,'seconds':seconds})
            row_hashes[name] = {p.name:s.q.r.digest(p) for p in directory.iterdir() if p.is_file()}
        cached = reported[name]
        assert all(cached[k]==v for k,v in {'status':status,'decision':d,'exactQuote':exact,'usage':usage,'seconds':seconds}.items())
        decisions[e['variant']][e['caseId']] = d
        quoted[e['variant']][e['caseId']] = d if d not in ['A','B'] or exact else 'NEITHER'
        outputs[name] = output
    labels = s.q.r.read(s.PANEL/'adjudicated-labels.private.json')
    all_panel = {v:{'strict':measure(labels,decisions[v]),'quoted':measure(labels,quoted[v])} for v in s.VARIANTS}
    common = {cid for cid in decisions['baseline'] if all(decisions[v][cid]!='UNSCORABLE' for v in s.VARIANTS)}
    common_labels = [l for l in labels if l['caseId'] in common]
    paired = {v:{'strict':measure(common_labels,{k:d for k,d in decisions[v].items() if k in common}),
        'quoted':measure(common_labels,{k:d for k,d in quoted[v].items() if k in common})} for v in s.VARIANTS}
    assert all_panel==report['allPanel'] and paired==report['paired'] and len(common)==report['commonCompleted']
    old = {x['caseId']:x for x in s.q.load('methods/baseline/development-judgments.private.json')}
    replay = {'availableComparisons':0,'sameStrictDecision':0,'sameFactualDecision':0,'sameCanonicalOutput':0}
    for cid in decisions['baseline']:
        if old[cid]['status']=='completed' and decisions['baseline'][cid]!='UNSCORABLE':
            new = outputs['baseline/'+cid]; prior = old[cid]['output']
            replay['availableComparisons'] += 1
            replay['sameStrictDecision'] += strict(new)==strict(prior)
            replay['sameFactualDecision'] += new['factualOutcome']==prior['factualOutcome']
            replay['sameCanonicalOutput'] += new==prior
    costs = {v:{'attemptedCalls':len(rs), 'unattemptedRules':60-len(rs),
        'inputTokens':known([(r['usage'] or {}).get('prompt_tokens') for r in rs]),
        'outputTokens':known([(r['usage'] or {}).get('completion_tokens') for r in rs]),
        'requestSeconds':known([r['seconds'] for r in rs])} for v,rs in accounting.items()}
    out = {'at':s.q.r.now(),'reviewerSourceSha256':s.q.r.digest(Path(__file__)),
        'rootAuditSha256':s.q.r.digest(root_report_path),'planSha256':PLAN_SHA,'rowHashes':row_hashes,
        'rawAuditedCalls':len(actual_starts),'unattemptedRuleRows':120-len(actual_starts),
        'allPanel':all_panel,'paired':paired,'commonCompleted':len(common),'execution':costs,
        'baselineReplayAgainstOldDevelopment':replay,'priorBaselineSha256':s.q.r.digest(s.q.ROOT/'methods/baseline/development-judgments.private.json'),
        'qualification':'Independent CPU-only reconciliation of exposed-development raw requests, model/usage/status and unchanged label joins. No new predictions, source edits or promotion. Baseline replay differences are diagnostics under concurrent scheduling, not model accuracy or proof of deterministic execution.'}
    s.c.once(HERE/'audit.private.json',out)
    print(json.dumps({k:v for k,v in out.items() if k not in ['rowHashes']},indent=2))


if __name__=='__main__':main()
