"""Autonomous Fable-generator / local-Qwen improvement loop for one private round.

Per method: automated prompt review -> guarded public-only rule draws ->
rule audit -> judge preflight -> local judge (4 workers) in parallel with
train-only teacher feedback -> audit -> report -> validation selection ->
optimize the next revision from the validation leader. Every phase runs
through the existing audited commands with immutable artifacts; a completed
phase is skipped on resume and an uncertain one halts the loop.

Stops on: wall-clock projection past the deadline, revision cap, two
consecutive revisions not allowed on validation, a hosted usage stop that the
transport could not wait out, a failed prompt review, an incomplete rule
cohort, or any failed phase. Never selects, freezes, or opens fixtures.
"""
import argparse, concurrent.futures, datetime, fcntl, json, os, re, subprocess, sys, time
from pathlib import Path
import qwen_round1 as q
import qwen_autorun as d
import qwen_guarded_rules as g
import fable_round
import fable_transport
from qwen_capacity_recovery import usage_limited

HERE = Path(__file__).parent
STOP_MARKER = 'fable-loop-stopped.json'
JUDGE_HOURS_DEFAULT = 3.3

def now(): return datetime.datetime.now(datetime.timezone.utc)

def log(**fields):
    print(json.dumps({'at': now().isoformat(), **fields}), flush=True)

def stop(reason, **fields):
    q.r.save(q.ROOT/STOP_MARKER, {'at': now().isoformat(), 'reason': reason, **fields})
    log(stopped=reason, **fields)
    raise SystemExit(reason)

def guards(protocol):
    fable_round.require_fable_root(); q.closed()
    if (q.ROOT/STOP_MARKER).exists(): raise RuntimeError('Loop previously stopped; reconcile '+STOP_MARKER)
    if g.stopped(): raise RuntimeError('Hosted usage stop marker present')
    record = fable_round.executable_record()
    if record['sha256'] != protocol['claudeExecutable']['sha256']: raise RuntimeError('Claude Code executable differs from protocol pin')
    ps = json.loads(subprocess.run(['/Users/wk/.lmstudio/bin/lms', 'ps', '--json'], capture_output=True, text=True, timeout=60).stdout or '[]')
    runtime = q.load('runtime.json')
    loaded = [m for m in ps if m.get('identifier') == runtime['identifier']]
    if len(ps) != 1 or not loaded or (loaded[0].get('contextLength') or loaded[0].get('loadConfig', {}).get('contextLength')) != runtime['contextLength']:
        raise RuntimeError('Pinned judge is not the single loaded LM Studio model with the pinned context')
    mine = ancestors()
    def foreign(line):
        pid, _, command = line.partition(' ')
        if not pid.isdigit() or int(pid) in mine or command.startswith(('caffeinate', 'nohup')): return False
        parent = subprocess.run(['ps', '-o', 'ppid=', '-p', pid], capture_output=True, text=True).stdout.strip()
        return not (parent.isdigit() and int(parent) in mine)
    others = [x for x in subprocess.run(['pgrep', '-fl', 'python.*(qwen_round1.py|qwen_guarded|fable_autorun|fable_round)'], capture_output=True, text=True).stdout.splitlines() if foreign(x)]
    if others: raise RuntimeError('Other round processes are running: '+'; '.join(others)[:500])

def phase_done(phase, method):
    root = q.ROOT/'driver'/method/phase
    if (root/'completed.json').exists():
        if q.r.read(root/'completed.json')['returncode'] == 0: return True
        raise RuntimeError('Failed phase retained; reconcile: '+str(root))
    if (root/'started.json').exists(): raise RuntimeError('Uncertain phase retained; reconcile: '+str(root))
    return False

def step(phase, method, args, tolerate_failure=False):
    root = q.ROOT/'driver'/method/phase
    if tolerate_failure and (root/'completed.json').exists():
        log(skip=phase, method=method, returncode=q.r.read(root/'completed.json')['returncode']); return
    if phase_done(phase, method):
        log(skip=phase, method=method); return
    try:
        d.command(phase, method, args)
    except RuntimeError:
        if not tolerate_failure: raise
        log(phaseFailedTolerated=phase, method=method)

def ancestors():
    pids, pid = set(), os.getpid()
    for _ in range(8):
        pids.add(pid)
        out = subprocess.run(['ps', '-o', 'ppid=', '-p', str(pid)], capture_output=True, text=True).stdout.strip()
        if not out.isdigit() or int(out) <= 1: break
        pid = int(out)
    return pids

def python(*args): return [sys.executable, *args]

# ---- feedback worker (child process) ------------------------------------------
def single_attempt(job, directory):
    """One hosted teacher attempt per shard; the transport itself waits out sign-in limits."""
    directory = Path(directory)
    if (directory/'teacher-effective.json').exists():
        original, effective = q.verify_teacher(directory)
        if original != job: raise RuntimeError('Completed shard input differs')
        return effective
    if g.stopped(): raise RuntimeError('Hosted training usage stop is active')
    if any((directory/name).exists() for name in ['model-request.json', 'parsed.json', 'process.json']):
        raise RuntimeError('Prior or uncertain attempt; no automatic retry')
    try: parsed = q.r.safe_call(job, directory)
    except RuntimeError:
        if not (directory/'parsed.json').exists(): raise
        parsed = q.r.read(directory/'parsed.json')
    if usage_limited(directory):
        q.once(g.STOP, {'at': q.r.now(), 'directory': str(directory), 'parsedSha256': q.r.digest(directory/'parsed.json'), 'reason': 'Sign-in usage limit that the transport could not wait out; no new hosted calls.'})
        raise RuntimeError('Usage limit; hosted training stopped')
    effective = {'selectedAttempt': 0, 'attempts': [{'directory': str(directory), 'status': parsed['status'], 'parsedSha256': q.r.digest(directory/'parsed.json')}],
                 'sameInputSha256': q.r.hash_value(job), 'output': parsed.get('output'), 'status': parsed['status']}
    if parsed['status'] != 'completed' or not isinstance(parsed.get('output'), dict):
        q.r.save(directory/'teacher-failed.json', effective); raise RuntimeError('Teacher shard failed; preserved: '+str(directory))
    q.r.save(directory/'teacher-effective.json', effective); return effective

def feedback_stopped(method):
    completion = q.ROOT/'driver'/method/'judge'/'completed.json'
    return g.stopped() or (completion.exists() and q.r.read(completion)['returncode'] != 0)

class FeedbackClock:
    def __init__(self, method, original): self.method, self.original = method, original
    def __getattr__(self, name): return getattr(self.original, name)
    def sleep(self, seconds):
        remaining = seconds
        while remaining > 0:
            if feedback_stopped(self.method): raise RuntimeError('Feedback stopped after failed judge or usage stop')
            self.original.sleep(min(1.0, remaining)); remaining -= min(1.0, remaining)

def feedback_worker(method, workers=3):
    original_clock, original_teacher = q.time, q.teacher_call
    def teacher(job, path):
        if feedback_stopped(method): raise RuntimeError('Feedback stopped')
        return single_attempt(job, path)
    q.time, q.teacher_call = FeedbackClock(method, original_clock), teacher
    try: q.distill(method, workers=workers, stream=True)
    finally: q.time, q.teacher_call = original_clock, original_teacher

# ---- one method ---------------------------------------------------------------
def method_cycle(method, leader, protocol, options):
    root = q.ROOT; mroot = root/'methods'/method
    if method != 'baseline' and not (root/(method+'.txt')).exists():
        step('optimize', method, python('qwen_round1.py', 'optimize', '--method', method, '--previous', leader, '--workers', '1'))
    fable_round.prompt_review(method)
    guarded = mroot/'guarded-generation-v1'
    if not (guarded/'plan.json').exists():
        step('guarded-rules-prepare', method, python('qwen_guarded_rules.py', 'prepare', '--method', method, '--workers', str(options['rule_workers'])))
    if not (guarded/'reviewed.json').exists():
        plan = q.r.read(guarded/'plan.json')
        if plan['workers'] > g.MAX_WORKERS or 'No automatic restart or retry' not in plan['procedure']: raise RuntimeError('Generation plan differs from the reviewed procedure')
        q.r.save(guarded/'reviewed.json', {'at': q.r.now(), 'approved': True, 'planSha256': q.r.digest(guarded/'plan.json'), 'review': 'Automated procedure review: bounded workers, unchanged public-only rule_job, no retry.'})
    if not (mroot/'rules.json').exists():
        step('guarded-rules-run', method, python('qwen_guarded_rules.py', 'run', '--method', method))
        if not (mroot/'rules.json').exists(): stop('incomplete_rule_cohort', method=method)
    if not (mroot/'rules-audit.json').exists(): step('rules-audit', method, python('qwen_round1.py', 'audit-rules', '--method', method))
    if not (mroot/'semantic-preflight-requests.private.json').exists(): step('preflight-inputs', method, python('qwen_round1.py', 'preflight', '--method', method))
    if not (mroot/'semantic-preflight.json').exists():
        step('preflight-tokens', method, ['node', 'qwen_preflight.mjs', str(mroot/'semantic-preflight-requests.private.json'), str(mroot/'semantic-preflight.json')])
    if not q.r.read(mroot/'semantic-preflight.json')['allFullInputsFit']: stop('preflight_inputs_do_not_fit', method=method)
    projected = options['last_judge_seconds'] or JUDGE_HOURS_DEFAULT*3600
    if not (mroot/'development-summary.json').exists() and time.time()+1.15*projected+45*60 > options['deadline']:
        stop('wall_clock_projection_exceeds_deadline', method=method, projectedSeconds=projected)
    judge_start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        judge = pool.submit(step, 'judge', method, python('qwen_round1.py', 'judge', '--method', method, '--workers', str(options['judge_workers'])))
        feedback = pool.submit(step, 'feedback', method, python('-c', f'import fable_autorun as f; f.feedback_worker({method!r}, workers={options["feedback_workers"]})'))
        judge.result(); feedback.result()
    if not (mroot/'development-summary.json').exists(): stop('judge_summary_missing', method=method)
    summary = q.r.read(mroot/'development-summary.json')
    failed = sum(v for k, v in summary['statuses'].items() if k in ['failed', 'transport_failed'])
    if failed > 0.01*sum(summary['statuses'].values()): stop('local_judge_failures', method=method, failed=failed)
    options['last_judge_seconds'] = summary.get('wallElapsedSeconds') or (time.time()-judge_start)
    step('audit', method, python('qwen_round1.py', 'audit'))
    step('report', method, python('qwen_round1.py', 'report'), tolerate_failure=True)
    selection = fable_round.validation_selection()
    log(method=method, validationLeader=selection['leader'], allowed=selection['allowed'], utility=summary.get('utility'), grounded=summary['metrics']['factual']['groundedFactualPasses'])
    return selection

def run(methods, wall_hours, rule_workers, judge_workers, feedback_workers, max_revisions):
    os.umask(0o077)
    protocol = q.load('protocol.json'); guards(protocol)
    lock = (q.ROOT/'.fable-round-owner.lock').open('a+'); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    options = {'rule_workers': rule_workers, 'judge_workers': judge_workers, 'feedback_workers': feedback_workers,
               'deadline': time.time()+wall_hours*3600, 'last_judge_seconds': None}
    leader, plateau, revisions = 'baseline', 0, 0
    d.status('starting', methods[0])
    try:
        for method in methods:
            if method != 'baseline':
                if revisions >= max_revisions: stop('revision_cap', revisions=revisions)
                if g.stopped(): stop('hosted_usage_stop')
            selection = method_cycle(method, leader, protocol, options)
            if method != 'baseline':
                revisions += 1
                plateau = 0 if method in selection['allowed'] else plateau+1
                if plateau >= 2: stop('plateau_two_revisions_not_allowed', lastMethod=method)
            leader = selection['leader']
            if time.time() > options['deadline']: stop('deadline_reached', lastMethod=method)
    except RuntimeError as exc:
        stop('phase_failed', error=str(exc)[:1000])
    d.status('methods-complete-awaiting-decision', methods[-1])
    log(done=True, leader=leader, revisions=revisions)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--methods', default='baseline,v1,v2,v3'); parser.add_argument('--wall-hours', type=float, default=12)
    parser.add_argument('--rule-workers', type=int, default=10); parser.add_argument('--judge-workers', type=int, default=4)
    parser.add_argument('--feedback-workers', type=int, default=3); parser.add_argument('--max-revisions', type=int, default=3)
    args = parser.parse_args()
    run(args.methods.split(','), args.wall_hours, args.rule_workers, args.judge_workers, args.feedback_workers, args.max_revisions)
