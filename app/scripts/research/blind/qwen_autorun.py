"""Continue two complete prompt revisions, pausing for agent prompt review.

Private artifacts are immutable; an uncertain/failed command is not silently
restarted. This driver never opens fresh fixtures or promotes a live method.
"""
import datetime,json,os,pathlib,subprocess,sys,time,threading,tempfile
import qwen_round1 as q

HERE=pathlib.Path(__file__).parent
STATUS_LOCK=threading.Lock()

def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def status(phase,method):
    value={'at':stamp(),'pid':os.getpid(),'phase':phase,'method':method}
    # The shared JSON helper uses a fixed temporary filename. Driver branches
    # have distinct artifacts, but this one status path needs serialization.
    with STATUS_LOCK:
        # Unique temporary files also protect this operational path if a
        # separate recovery coordinator overlaps an older process at exit.
        fd,name=tempfile.mkstemp(prefix='.driver-progress-',suffix='.tmp',dir=q.ROOT)
        try:
            with os.fdopen(fd,'w') as stream:json.dump(value,stream,indent=2)
            os.replace(name,q.ROOT/'DRIVER-PROGRESS.json')
        finally:
            if os.path.exists(name):os.unlink(name)
        print(json.dumps(value),flush=True)

def await_file(path,phase,method):
    status(phase,method)
    while not path.exists():time.sleep(15)

def command(phase,method,args):
    root=q.ROOT/'driver'/method/phase;root.mkdir(parents=True,exist_ok=True)
    if (root/'started.json').exists():raise RuntimeError('Prior/uncertain driver action must be reconciled: '+str(root))
    status(phase,method)
    q.r.save(root/'started.json',{'at':stamp(),'args':args,'cwd':str(HERE)})
    with (root/'output.log').open('x') as log:
        process=subprocess.Popen(args,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
        q.r.save(root/'process.json',{'pid':process.pid})
        code=process.wait()
    q.r.save(root/'completed.json',{'at':stamp(),'returncode':code,'logSha256':q.r.digest(root/'output.log')})
    if code:raise RuntimeError('Driver action failed; preserved: '+str(root))

def revisions(methods,previous):
    for method in methods:
        command('optimize',method,[sys.executable,'qwen_round1.py','optimize','--method',method,'--previous',previous,'--workers','1'])
        await_file(q.ROOT/('prompt-reviewed-'+method+'.json'),'awaiting-agent-prompt-review',method)
        review=q.load('prompt-reviewed-'+method+'.json')
        if not review['approved'] or review['generatorSha256']!=q.r.digest(q.ROOT/(method+'.txt')) or review['judgeSha256']!=q.r.digest(q.ROOT/(method+'-judge.txt')):raise RuntimeError('Prompt review does not match exact prompts')
        command('rules',method,[sys.executable,'qwen_round1.py','rules','--method',method,'--workers','12'])
        command('rules-audit',method,[sys.executable,'qwen_round1.py','audit-rules','--method',method])
        command('preflight-inputs',method,[sys.executable,'qwen_round1.py','preflight','--method',method])
        command('preflight-tokens',method,['node','qwen_preflight.mjs',str(q.ROOT/'methods'/method/'semantic-preflight-requests.private.json'),str(q.ROOT/'methods'/method/'semantic-preflight.json')])
        # Inference and full-evidence distillation are independent, bounded jobs.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            judge=pool.submit(command,'judge',method,[sys.executable,'qwen_round1.py','judge','--method',method,'--workers','4'])
            feedback=pool.submit(command,'feedback',method,[sys.executable,'-c',f'import qwen_round1 as q; q.distill({method!r},workers=3,stream=True)'])
            judge.result();feedback.result()
        command('audit',method,[sys.executable,'qwen_round1.py','audit'])
        command('report',method,[sys.executable,'qwen_round1.py','report'])
        previous=method
    status('two-revisions-complete-awaiting-plateau-review','v2')

def resume_unstarted_v1_feedback(prior_pid):
    """One declared coordinator recovery; never restart the existing judge."""
    import concurrent.futures
    os.umask(0o077)
    if (q.ROOT/'driver/v1/feedback/started.json').exists():raise RuntimeError('Feedback already started; reconcile first')
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        feedback=pool.submit(command,'feedback','v1',[sys.executable,'-c',"import qwen_round1 as q; q.distill('v1',workers=3,stream=True)"])
        await_file(q.ROOT/'driver/v1/judge/completed.json','awaiting-existing-judge','v1')
        judge=q.load('driver/v1/judge/completed.json')
        if judge['returncode']:raise RuntimeError('Existing judge failed; preserve and reconcile')
        while True:
            try:os.kill(prior_pid,0)
            except ProcessLookupError:break
            time.sleep(2)
        feedback.result()
    command('audit','v1',[sys.executable,'qwen_round1.py','audit'])
    command('report','v1',[sys.executable,'qwen_round1.py','report'])
    revisions(['v2'],'v1')

def resume_partitioned_v1_feedback(prior_pids,phase='feedback-case-partition-v1'):
    """Declared failed feedback recovery; retain the existing inference owner."""
    import concurrent.futures
    os.umask(0o077)
    amendment=q.load('feedback-case-partition-amendment-v1.json')
    if q.load('driver/v1/feedback/completed.json')['returncode']!=1:raise RuntimeError('Expected preserved feedback failure')
    for name,sha in amendment['preservedPriorTeacherFileHashes'].items():
        if q.r.digest(q.ROOT/name)!=sha:raise RuntimeError('Completed teacher inputs changed before recovery')
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        feedback=pool.submit(command,phase,'v1',[sys.executable,'-c',"import qwen_round1 as q; q.distill('v1',workers=3,stream=True)"])
        await_file(q.ROOT/'driver/v1/judge/completed.json','awaiting-existing-judge-partition-recovery','v1')
        if q.load('driver/v1/judge/completed.json')['returncode']:raise RuntimeError('Existing judge failed; preserve and reconcile')
        for pid in prior_pids:
            while True:
                try:os.kill(pid,0)
                except ProcessLookupError:break
                time.sleep(2)
        feedback.result()
    command('audit','v1',[sys.executable,'qwen_round1.py','audit'])
    command('report','v1',[sys.executable,'qwen_round1.py','report'])
    revisions(['v2'],'v1')

def run():
    os.umask(0o077)
    await_file(q.ROOT/'methods/baseline/development-summary.json','awaiting-existing-baseline','baseline')
    await_file(q.ROOT/'feedback/baseline/manifest.json','awaiting-existing-feedback','baseline')
    revisions(['v1','v2'],'baseline')

if __name__=='__main__':run()
