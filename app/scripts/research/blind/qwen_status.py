"""Content-free progress for the private Qwen development experiment."""
import collections,datetime,json,statistics
import qwen_round1 as q

def main():
    now=datetime.datetime.now(datetime.timezone.utc)
    items={x['caseId']:x for x in q.load(q.ITEMS)}
    methods={}
    for method in sorted((q.ROOT/'methods').iterdir()):
        if not method.is_dir():continue
        results=[];starts=[];pending=[]
        for path in (method/'development').glob('*/*/started.json'):
            at=datetime.datetime.fromisoformat(q.r.read(path)['at']);starts.append(at)
            result=path.parent/'result.json'
            if result.exists():results.append({**q.r.read(result),'kind':items[path.parent.parent.name]['kind']})
            else:pending.append((now-at).total_seconds())
        summary_path=method/'development-summary.json';summary=q.r.read(summary_path) if summary_path.exists() else None
        elapsed=summary.get('wallElapsedSeconds',0) if summary else (now-min(starts)).total_seconds() if starts else 0
        kinds={}
        for kind in ['control','factual','weak','unlabeled']:
            rows=[x for x in results if x['kind']==kind];times=[x['seconds'] for x in rows]
            kinds[kind]={'calls':len(rows),'statuses':dict(collections.Counter(x['status'] for x in rows)),'medianSeconds':statistics.median(times) if times else None}
        generations=[q.r.read(p) for p in (method/'rules').glob('*/*/parsed.json')]
        feedback=q.ROOT/'feedback'/method.name
        methods[method.name]={'completedReport':summary is not None,'completedCalls':len(results),'pendingCalls':len(pending),
            'longestPendingSeconds':max(pending,default=0),'elapsedSeconds':elapsed,'observedCallsPerHour':len(results)/elapsed*3600 if elapsed else None,'byKind':kinds,
            'ruleGeneration':{'finished':len(generations),'planned':241,'statuses':dict(collections.Counter(x['status'] for x in generations))},
            'feedback':{'completedShards':len(list(feedback.glob('*/teacher-effective.json'))),'startedShards':len(list(feedback.glob('*/job.json'))),'complete':(feedback/'manifest.json').exists()},
            'throughputCaution':'Grouped complete semantic email prefixes make partial-run throughput unrepresentative. Completed methods use their frozen actual wall duration.'}
    output={'at':now.isoformat(),'methods':methods};q.r.save(q.ROOT/'PROGRESS.json',output);print(json.dumps(output),flush=True)

if __name__=='__main__':main()
