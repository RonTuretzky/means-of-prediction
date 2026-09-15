"""Prepare and score a Claude Fable 5.1 generator round in its own private root.

`prepare` creates the new root from byte-identical copies of the Astra round's
frozen development inputs (items, seals, runtime pin, reservations), writes the
Astra-identical baseline prompts so the generator/teacher model is the only
changed variable, seals a market/group-level validation split before any hosted
call, and records the protocol. `prompt-review` is the automated lexical gate
that replaces the earlier agent review. `validation-selection` scores completed
methods on validation rows only and names the leader that the next revision
chains from. `effort-probe` measures latency/cost per effort on development
public questions without scoring.

Requires MOP_QWEN_ROOT to point at a root whose name starts with 'fable-'.
"""
import argparse, collections, concurrent.futures, hashlib, json, os, shutil, statistics, subprocess, sys
from pathlib import Path
import qwen_round1 as q
import fable_transport

REQUIRED_INPUTS = ['public-inputs.json', 'development-cases.private.json', 'development-corpus.private.json',
                   'expansion-cases.private.json', 'followup-cases.private.json', 'holdout-public.json', 'controls.private.json',
                   'development-items.private.json', 'development-items-seal.json', 'development-items-semantic.private.json',
                   'semantic-item-render-audits.private.json', 'semantic-development-seal.json', 'runtime.json']
OPTIONAL_INPUTS = ['independent-holdout-public.json', 'independent-public-reservation.json', 'independent-fixture-seal.json',
                   'independent-evaluation-amendment.json', 'data-amendment.json']
GENERATOR_FIELDS = ['factualA', 'factualB', 'settlementA', 'settlementB', 'abstainWhen', 'limitations']
JUDGE_FIELDS = ['factualOutcome', 'outcomeA', 'outcomeB', 'evidenceQuote', 'missingConditions']
PROMPT_LIMITS = {'generator': 12000, 'judge': 14000}
VALIDATION_TARGET = {'factualMin': 40, 'factualMax': 60, 'controlMin': 400, 'controlMax': 520}
MARGINS = {'groundedFactualPasses': 3, 'strictPositivePasses': 8}

def require_fable_root():
    if not q.FABLE_ROUND or not q.ROOT.name.startswith('fable-'):
        raise RuntimeError('MOP_QWEN_ROOT must name a fable-* round root')
    return q.ROOT

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def executable_record():
    binary = fable_transport.executable()
    version = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=60).stdout.strip()
    return {'path': binary, 'version': version, 'sha256': sha(binary)}

# ---- validation split -------------------------------------------------------
def validation_split(items, cases, target=VALIDATION_TARGET):
    """Deterministic market/group units; validation labels are withheld from the teacher.

    Factual markets travel with their development groupId (every market of the
    group and all rows on those markets); other markets are their own unit.
    Units are visited in sha256(unit key) order and added to validation until
    the factual and control targets are met, never exceeding the caps.
    """
    group_of = {c['marketId']: c['groupId'] for c in cases}
    units = collections.defaultdict(set)
    for item in items:
        key = 'group:'+group_of[item['marketId']] if item['marketId'] in group_of else 'market:'+item['marketId']
        units[key].add(item['marketId'])
    by_market = collections.defaultdict(list)
    for item in items: by_market[item['marketId']].append(item)
    order = sorted(units, key=lambda k: hashlib.sha256(k.encode()).hexdigest())
    chosen, counts = [], collections.Counter()
    for key in order:
        rows = [row for mid in sorted(units[key]) for row in by_market[mid]]
        add = collections.Counter(row['kind'] for row in rows)
        if counts['factual']+add['factual'] > target['factualMax'] or counts['control']+add['control'] > target['controlMax']:
            continue
        chosen.append(key); counts.update(add)
        if counts['factual'] >= target['factualMin'] and counts['control'] >= target['controlMin']:
            break
    validation = sorted(row['caseId'] for key in chosen for mid in sorted(units[key]) for row in by_market[mid])
    held = set(validation)
    train = collections.Counter(row['kind'] for row in items if row['caseId'] not in held)
    return {'protocol': 'market-group-units-v1', 'target': target, 'unitOrder': 'sha256(unit key)', 'units': chosen,
            'validationMarketIds': sorted(mid for key in chosen for mid in units[key]), 'validationCaseIds': validation,
            'validationCounts': dict(counts), 'trainCounts': dict(train), 'totalUnits': len(units),
            'limitation': 'Rows are one connected component through shared emails; validation market labels are withheld, but validation email bodies may still appear in train rows of other markets.'}

# ---- prompt review ----------------------------------------------------------
def leak_terms(root):
    terms = set()
    for p in q.r.read(root/'public-inputs.json'): terms.add(str(p['marketId']))
    for c in q.r.read(root/'development-cases.private.json'):
        for key in ['emailId', 'factKey']:
            if c.get(key): terms.add(str(c[key]))
    for e in q.r.read(root/'development-corpus.private.json'):
        subject = (e.get('subject') or '').strip()
        if len(subject) >= 12: terms.add(subject)
        if e.get('id'): terms.add(str(e['id']))
    return terms

def review_prompts(generator, judge, terms):
    checks = {'generatorNonEmpty': bool(generator.strip()), 'judgeNonEmpty': bool(judge.strip()),
              'generatorFields': all(f in generator for f in GENERATOR_FIELDS), 'judgeFields': all(f in judge for f in JUDGE_FIELDS),
              'generatorLength': len(generator) <= PROMPT_LIMITS['generator'], 'judgeLength': len(judge) <= PROMPT_LIMITS['judge'],
              'noPrivateIdentifiers': not any(t in generator or t in judge for t in terms),
              'noAnswerTable': not any(marker in generator for marker in ['expectedOutcome', 'lookup table', 'answer key'])}
    return checks, all(checks.values())

def prompt_review(method):
    root = require_fable_root(); marker = root/('prompt-reviewed-'+method+'.json')
    generator, judge = (root/(method+'.txt')).read_text(), (root/(method+'-judge.txt')).read_text()
    if marker.exists():
        review = q.r.read(marker)
        if review['generatorSha256'] != sha(root/(method+'.txt')) or review['judgeSha256'] != sha(root/(method+'-judge.txt')):
            raise RuntimeError('Existing prompt review does not match current prompts')
        return review
    checks, approved = review_prompts(generator, judge, leak_terms(root))
    review = {'at': q.r.now(), 'approved': approved, 'generatorSha256': sha(root/(method+'.txt')), 'judgeSha256': sha(root/(method+'-judge.txt')),
              'review': 'Automated lexical review v1: schema fields present, length caps, no market IDs, email IDs, fact keys or subjects from development data, no answer tables.',
              'checks': checks}
    q.once(('prompt-reviewed-' if approved else 'prompt-review-failed-')+method+'.json', review)
    if not approved:
        raise RuntimeError('Prompt review failed for '+method+': '+json.dumps(checks))
    return review

# ---- validation scoring -----------------------------------------------------
def subset_summary(rows):
    groups = {kind: [x for x in rows if x['kind'] == kind] for kind in ['factual', 'control', 'weak', 'unlabeled']}
    def metrics(xs):
        positive = [x for x in xs if x['expected'] in ['A', 'B']]; negative = [x for x in xs if x['kind'] == 'control' and x['expected'] not in ['A', 'B']]
        return {'total': len(xs), 'completed': sum(x['valid'] for x in xs), 'positiveTotal': len(positive),
                'factualPasses': sum(x['factualPass'] is True for x in positive), 'groundedFactualPasses': sum(x['groundedFactualPass'] is True for x in positive),
                'strictPositivePasses': sum(x['strictPass'] is True for x in positive), 'negativeTotal': len(negative), 'falsePositives': sum(x['falsePositive'] is True for x in negative),
                'wrongOutcomes': sum(x['wrongOutcome'] is True for x in xs), 'wrongFactualOutcomes': sum(x['wrongFactualOutcome'] is True for x in xs),
                'conflicts': sum(x['conflict'] for x in xs), 'unscorable': sum(not x['valid'] for x in xs)}
    summary = {'metrics': {k: metrics(v) for k, v in groups.items()}, 'rows': len(rows)}
    families = collections.defaultdict(list)
    for x in groups['factual']: families[x['metadata']['factKey']].append(x)
    summary['factFamilyMacroRecall'] = sum(sum(x['groundedFactualPass'] for x in xs)/len(xs) for xs in families.values())/len(families) if families else 0
    summary['factFamilies'] = len(families)
    c = summary['metrics']['control']
    summary['utility'] = summary['factFamilyMacroRecall']+c['strictPositivePasses']/max(1, c['positiveTotal'])-3*c['falsePositives']/max(1, c['negativeTotal'])-sum(not x['valid'] for x in rows)/max(1, len(rows))
    return summary

def validation_selection(write=True):
    root = require_fable_root(); held = q.validation_ids()
    if not held: raise RuntimeError('validation-split.json missing')
    methods = sorted(p.parent.name for p in (root/'methods').glob('*/development-summary.json'))
    if 'baseline' not in methods: raise RuntimeError('Baseline not complete')
    summaries = {m: subset_summary([x for x in q.load('methods/'+m+'/development-scores.private.json') if x['caseId'] in held]) for m in methods}
    base = summaries['baseline']; verdicts = {}
    for m in methods:
        if m == 'baseline': continue
        paired = q.comparison(m, subset=held); a, b = paired['candidate'], paired['baseline']
        margins = {'groundedFactualPasses': a['groundedFactualPasses']-b['groundedFactualPasses'] >= MARGINS['groundedFactualPasses'],
                   'strictPositivePasses': a['strictPositivePasses']-b['strictPositivePasses'] >= MARGINS['strictPositivePasses'],
                   'falsePositives': a['falsePositives'] <= b['falsePositives']}
        verdicts[m] = {'eligible': q.eligible(summaries[m], base), 'pairedStrictImprovement': paired['pairedStrictImprovement'], 'margins': margins,
                       'allowed': q.eligible(summaries[m], base) and paired['pairedStrictImprovement'] and all(margins.values()), 'paired': paired}
    allowed = [m for m, v in verdicts.items() if v['allowed']]
    leader = max(allowed, key=lambda m: summaries[m]['utility']) if allowed else 'baseline'
    result = {'at': q.r.now(), 'validationRows': len(held), 'methods': methods, 'summaries': summaries, 'verdicts': verdicts, 'allowed': allowed, 'leader': leader,
              'margins': MARGINS, 'rule': 'Leader = highest validation utility among methods passing eligibility, paired strict improvement and predeclared margins on validation rows; else baseline.'}
    if write: q.r.save(root/'validation-selection.json', result)
    return result

# ---- prepare ----------------------------------------------------------------
def prepare(source, rule_effort='medium'):
    root = require_fable_root(); source = Path(source)
    if root.exists(): raise RuntimeError('Round root exists; use a new root')
    if source.resolve() == root.resolve(): raise RuntimeError('Source and root coincide')
    os.umask(0o077); root.mkdir(parents=True, mode=0o700)
    provenance = {'source': str(source), 'files': {}}
    for name in REQUIRED_INPUTS+OPTIONAL_INPUTS:
        path = source/name
        if not path.exists():
            if name in REQUIRED_INPUTS: raise RuntimeError('Missing frozen input: '+name)
            continue
        shutil.copyfile(path, root/name); os.chmod(root/name, 0o600)
        if sha(root/name) != sha(path): raise RuntimeError('Copy differs: '+name)
        provenance['files'][name] = {'sha256': sha(path), 'bytes': path.stat().st_size}
    seal = q.r.read(root/'semantic-development-seal.json')
    if seal['itemsSha256'] != sha(root/q.ITEMS) or seal['rendererSha256'] != sha(Path(q.semantic.__file__)):
        raise RuntimeError('Semantic seal does not bind the copied items or the current renderer')
    (root/'baseline.txt').write_text(q.BASE_PROMPT); (root/'baseline-judge.txt').write_text(q.BASE_JUDGE)
    items = q.load(q.ITEMS); cases = q.load('development-cases.private.json')
    split = validation_split(items, cases); split['createdAt'] = q.r.now(); split['itemsSha256'] = seal['itemsSha256']
    q.once('validation-split.json', split)
    q.once('input-provenance.json', provenance)
    here = Path(__file__).parent
    protocol = {'createdAt': q.r.now(), 'round': root.name, 'generator': fable_transport.MODEL, 'transport': fable_transport.PROVIDER,
                'generatorLabel': q.GENERATOR_LABEL, 'ruleEffort': rule_effort, 'teacherEffort': 'high', 'hostedBudgetsUsd': q.HOSTED_BUDGETS_USD,
                'hostedLimitPolicy': {'policy': fable_transport.LIMIT_POLICY, 'maxWaits': fable_transport.MAX_LIMIT_WAITS, 'maxWaitSeconds': fable_transport.MAX_LIMIT_WAIT_SECONDS,
                                      'authorization': 'User instruction 2026-09-15: keep the experiment running for at least twelve hours; waiting for a sign-in limit reset is authorized.'},
                'claudeExecutable': executable_record(), 'python': sys.version.split()[0],
                'sourceHashes': {name: sha(here/name) for name in ['fable_transport.py', 'fable_round.py', 'fable_autorun.py', 'qwen_round1.py', 'round4.py', 'improve.py', 'experiment.py', 'qwen_guarded_rules.py', 'qwen_capacity_recovery.py', 'qwen_semantic.py', 'qwen_preflight.mjs'] if (here/name).exists()},
                'baselinePromptSha256': sha(root/'baseline.txt'), 'baselineJudgeSha256': sha(root/'baseline-judge.txt'),
                'validationSplitSha256': sha(root/'validation-split.json'), 'inputProvenanceSha256': sha(root/'input-provenance.json'),
                'selectionRule': 'Validation-only leader with predeclared margins; final select() intersects with full-development gates. No live promotion.',
                'residualGeneratorContext': 'Headless Claude Code adds a signed-in user email reminder and an environment block (temp dir, platform, date, model) to each call; one Haiku bookkeeping side-call per run is recorded in modelUsage.',
                'judge': 'Unchanged pinned local Qwen3.5-35B-A3B (runtime.json copied byte-identical).'}
    q.once('protocol.json', protocol)
    print(json.dumps({'root': str(root), 'copied': len(provenance['files']), 'itemsSha256': seal['itemsSha256'][:12], 'validation': split['validationCounts'], 'train': split['trainCounts'],
                      'baselinePromptSha256': protocol['baselinePromptSha256'][:12], 'claude': protocol['claudeExecutable']['version']}), flush=True)

# ---- effort probe -----------------------------------------------------------
def effort_probe(efforts, questions, workers, out):
    """Unscored latency/cost probe on development public questions; writes outside any round root."""
    import improve
    out = Path(out); out.mkdir(parents=True, exist_ok=True, mode=0o700)
    public = sorted(q.load('public-inputs.json'), key=lambda p: p['marketId'])[:questions]
    contexts = q.r.load('public-contexts.json')
    tasks = [(effort, p) for effort in efforts for p in public]
    def one(task):
        effort, p = task; job = {**q.rule_job(p, q.BASE_PROMPT, contexts.get(p['marketId'])), 'effort': effort}
        directory = out/effort/p['marketId']
        try: parsed = improve.invoke(job, directory)
        except RuntimeError: parsed = q.r.read(directory/'parsed.json') if (directory/'parsed.json').exists() else {'status': 'failed', 'output': None}
        result = q.r.read(directory/'transport-result.json') if (directory/'transport-result.json').exists() else {}
        return {'effort': effort, 'marketId': p['marketId'], 'status': parsed['status'], 'seconds': result.get('seconds'), 'costUsd': result.get('costUsd'),
                'outputChars': len(json.dumps(parsed.get('output') or {})), 'outputTokens': (result.get('events') or [{}])[-1].get('usage', {}).get('output_tokens')}
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(one, tasks):
            rows.append(row); print(json.dumps(row), flush=True)
    summary = {}
    for effort in efforts:
        xs = [x for x in rows if x['effort'] == effort]; ok = [x for x in xs if x['status'] == 'completed']
        med = lambda key: statistics.median([x[key] for x in ok if x.get(key) is not None]) if ok else None
        summary[effort] = {'draws': len(xs), 'completed': len(ok), 'medianSeconds': med('seconds'), 'medianCostUsd': med('costUsd'), 'medianOutputChars': med('outputChars'), 'medianOutputTokens': med('outputTokens'),
                           'statuses': dict(collections.Counter(x['status'] for x in xs))}
    q.r.save(out/'summary.json', {'at': q.r.now(), 'questions': questions, 'rows': rows, 'summary': summary})
    print(json.dumps(summary, indent=1), flush=True)

if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--source', required=True); p.add_argument('--rule-effort', default='medium')
    p = sub.add_parser('prompt-review'); p.add_argument('--method', required=True)
    sub.add_parser('validation-selection')
    p = sub.add_parser('effort-probe'); p.add_argument('--efforts', default='low,medium,high'); p.add_argument('--questions', type=int, default=12); p.add_argument('--workers', type=int, default=6); p.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.action == 'prepare': prepare(args.source, args.rule_effort)
    elif args.action == 'prompt-review': print(json.dumps(prompt_review(args.method)), flush=True)
    elif args.action == 'validation-selection': print(json.dumps({k: v for k, v in validation_selection().items() if k in ['allowed', 'leader', 'validationRows', 'methods']}), flush=True)
    elif args.action == 'effort-probe': effort_probe(args.efforts.split(','), args.questions, args.workers, args.out)
