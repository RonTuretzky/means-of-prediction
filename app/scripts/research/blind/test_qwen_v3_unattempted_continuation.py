import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import qwen_v3_unattempted_continuation as c


def runtime():
    info = {'identifier':'pinned', 'modelKey':'key', 'format':'gguf', 'path':'model.gguf',
            'sizeBytes':20, 'architecture':'arch', 'quantization':{'name':'Q4_K_M'}, 'contextLength':100,
            'status':'idle', 'queued':0}
    return {'identifier':'pinned', 'contextLength':100, 'loadedModels':[info],
            'lmStudioVersion':'v', 'engines':'engine', 'artifactSha256':'sha', 'artifactBytes':20}


def snapshot():
    r = runtime()
    return {'modelsBefore':copy.deepcopy(r['loadedModels']), 'modelsAfter':copy.deepcopy(r['loadedModels']),
            'sdk':{'modelInfo':copy.deepcopy(r['loadedModels'][0]), 'loadConfig':{'fields':[
                {'key':'llm.load.numParallelSessions','value':4}, {'key':'llm.load.contextLength','value':100},
                {'key':'llm.load.llama.acceleration.offloadRatio','value':1}]}},
            'appVersion':'v', 'engines':'engine', 'artifactSha256':'sha', 'loadedArtifactSha256':'sha', 'artifactBytes':20}


class ContinuationTests(unittest.TestCase):
    def test_idle_and_four_slots_required(self):
        c.validate_runtime(snapshot(), runtime())
        for key, value in [('status','predicting'), ('queued',1), ('queued',None)]:
            s = snapshot();s['modelsAfter'][0][key] = value
            with self.assertRaises(RuntimeError):c.validate_runtime(s, runtime())
        s = snapshot();s['sdk']['loadConfig']['fields'][0]['value'] = 8
        with self.assertRaises(RuntimeError):c.validate_runtime(s, runtime())

    def test_model_context_engine_and_loaded_bytes_bound(self):
        for mutate in [lambda s:s['sdk']['modelInfo'].update(identifier='other'),
                       lambda s:s['modelsBefore'][0].update(contextLength=99),
                       lambda s:s.update(loadedArtifactSha256='other'),
                       lambda s:s.update(engines='new'), lambda s:s.update(appVersion='new')]:
            s = snapshot();mutate(s)
            with self.assertRaises(RuntimeError):c.validate_runtime(s, runtime())

    def test_full_load_config_bound_after_preparation(self):
        s = snapshot();expected = copy.deepcopy(s['sdk']['loadConfig'])
        s['sdk']['loadConfig']['fields'].append({'key':'other','value':True})
        with self.assertRaises(RuntimeError):c.validate_runtime(s, runtime(), expected)

    def test_duplicate_load_fields_rejected(self):
        s = snapshot();s['sdk']['loadConfig']['fields'].append(s['sdk']['loadConfig']['fields'][0])
        with self.assertRaises(RuntimeError):c.validate_runtime(s, runtime())

    def test_retired_owners_must_be_dead(self):
        with patch.object(c.os, 'kill', side_effect=ProcessLookupError):c.dead([10,11])
        with patch.object(c.os, 'kill'):
            with self.assertRaises(RuntimeError):c.dead([10])
        for values in [[],[10,10],[True],[0]]:
            with self.assertRaises(RuntimeError):c.dead(values)

    def test_exact_194_excludes_uncertain_and_reordering(self):
        entries = [{'ordinal':n,'caseId':str(n),'started':None,'artifactHashes':{}} for n in range(1721,1915)]
        rec = {'unattemptedRequests':entries,'uncertainRequests':[{'caseId':'1717'}]}
        with patch.object(c.q, 'load', return_value={'requests':entries}):
            self.assertEqual(c.expected_entries(rec), entries)
            bad = copy.deepcopy(entries);bad[0]['caseId']='1717'
        for mutate in [lambda x:x.reverse(), lambda x:x.pop(), lambda x:x[0].update(caseId='1717'), lambda x:x[0].update(started={})]:
            bad=copy.deepcopy(entries);mutate(bad)
            with patch.object(c.q, 'load', return_value={'requests':bad}):
                with self.assertRaises(RuntimeError):c.expected_entries({**rec,'unattemptedRequests':bad})

    def test_any_original_or_new_target_artifact_blocks_first_attempt(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(c, 'ROOT', Path(d)/'new'), patch.object(c.q,'ROOT',Path(d)/'old'):
                e={'caseId':'x'};c.check_unattempted(e)
                original=c.original_path('x');original.mkdir(parents=True)
                with self.assertRaises(RuntimeError):c.check_unattempted(e)
                original.rmdir();(c.ROOT/'responses/x').mkdir(parents=True)
                with self.assertRaises(RuntimeError):c.check_unattempted(e)

    def test_attempt_is_once_and_does_not_touch_original(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(c,'ROOT',Path(d)/'new'), patch.object(c.q,'ROOT',Path(d)/'old'), patch.object(c.q,'local_call',return_value={'status':'completed'}) as call, patch.object(c,'verify_response'):
                e={'caseId':'x','ordinal':1721,'requestSha256':'s'}
                c.attempt(e, {'model':'pinned'}, threading.Event())
                with self.assertRaises(RuntimeError):c.attempt(e, {'model':'pinned'}, threading.Event())
                self.assertEqual(call.call_count,1)
                self.assertFalse(c.original_path('x').exists())
                self.assertTrue((c.ROOT/'responses/x/dispatch-started.json').exists())

    def test_stopped_worker_never_calls(self):
        stop=threading.Event();stop.set()
        with patch.object(c.q,'local_call') as call:
            with self.assertRaises(RuntimeError):c.attempt({'caseId':'x'}, {}, stop)
            call.assert_not_called()

    def test_feeder_drains_inflight_but_dispatches_no_replacements_on_error(self):
        started=[];barrier=threading.Barrier(4);drained=[]
        entries=[{'caseId':str(i)} for i in range(20)]
        def worker(e,request,stop):
            started.append(e['caseId']);barrier.wait(timeout=3)
            if e['caseId']=='0':raise RuntimeError('Integrity failure')
            while not stop.is_set():time.sleep(.001)
            drained.append(e['caseId'])
        result=c.feed(entries,{e['caseId']:{} for e in entries},worker)
        self.assertEqual(set(started),{'0','1','2','3'})
        self.assertEqual(set(drained),{'1','2','3'})
        self.assertTrue(result['stopped']);self.assertEqual(len(result['errors']),1)

    def test_feeder_success_uses_each_request_once_with_bounded_concurrency(self):
        lock=threading.Lock();active=0;peak=0;seen=[]
        entries=[{'caseId':str(i)} for i in range(11)]
        def worker(e,request,stop):
            nonlocal active,peak
            with lock:active+=1;peak=max(peak,active);seen.append(e['caseId'])
            time.sleep(.002)
            with lock:active-=1
        result=c.feed(entries,{e['caseId']:{} for e in entries},worker)
        self.assertEqual(set(seen),set(str(i) for i in range(11)))
        self.assertEqual(len(seen),11);self.assertLessEqual(peak,4);self.assertFalse(result['stopped'])

    def test_external_review_requires_exact_plan_ownership_and_old_pids(self):
        review={'approved':True,'planSha256':'sha','noCompetingLocalInference':True,
                'preserveOriginalIncompleteRun':True,'retiredProcessIds':c.OLD_PIDS}
        with patch.object(c.q.r,'read',return_value=review),patch.object(c.q.r,'digest',return_value='sha'),patch.object(c,'dead'):
            c.review_gate({})
        for key,value in [('planSha256','other'),('noCompetingLocalInference',False),('preserveOriginalIncompleteRun',False),('retiredProcessIds',[])]:
            with patch.object(c.q.r,'read',return_value={**review,key:value}),patch.object(c.q.r,'digest',return_value='sha'),patch.object(c,'dead'):
                with self.assertRaises(RuntimeError):c.review_gate({})

    def test_original_inventory_detects_new_and_missing_files(self):
        with tempfile.TemporaryDirectory() as d,patch.object(c.q,'ROOT',Path(d)):
            p=Path(d)/'methods/v3/a';p.parent.mkdir(parents=True);p.write_text('x')
            first=c.original_inventory();p.write_text('y')
            self.assertNotEqual(c.original_inventory(),first)
            p.unlink();self.assertEqual(c.original_inventory(),{})

    def test_accounting_retains_missing_input_output_and_duration(self):
        result=c.execution([{'usage':{'prompt_tokens':5},'seconds':3},{'usage':{'completion_tokens':7}},{}])
        self.assertEqual(result['inputTokens'],{'knownTotal':5,'missing':2,'isLowerBound':True})
        self.assertEqual(result['outputTokens'],{'knownTotal':7,'missing':2,'isLowerBound':True})
        self.assertEqual(result['requestSeconds'],{'knownTotal':3,'missing':2,'isLowerBound':True})

    def test_interrupted_original_scores_unscorable_never_negative(self):
        item={'caseId':'x','marketId':'m','kind':'control','expected':'B','email':{'completeSemanticText':'body'},'metadata':{}}
        score=c.q.score_record(item,{'status':'interrupted_unscorable','output':None,'trial':1})
        self.assertFalse(score['valid']);self.assertEqual(score['settlementOutcome'],'UNSCORABLE')
        self.assertFalse(score['strictPass']);self.assertFalse(score['wrongOutcome'])

    def test_failed_response_metadata_is_raw_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);request={'model':'pinned'}
            raw={'model':'pinned','choices':[{'finish_reason':'length','message':{'content':'{','reasoning_content':''}}], 'usage':{'prompt_tokens':10,'completion_tokens':2048}}
            c.q.r.save(d/'request.json',request);c.q.r.save(d/'response.json',raw);(d/'response.raw').write_text(json.dumps(raw))
            result={'status':'failed','output':None,'httpStatus':200,'finishReason':'length','usage':raw['usage'],'returnedModel':'pinned','reasoningCharacters':0,'requestSha256':c.q.r.hash_value(request),'responseSha256':c.q.r.digest(d/'response.json'),'rawResponseSha256':c.q.r.digest(d/'response.raw')}
            c.q.r.save(d/'result.json',result);c.verify_response(d,request,result)
            for key,value in [('returnedModel','wrong'),('usage',{}),('finishReason','stop'),('reasoningCharacters',2)]:
                changed={**result,key:value};c.q.r.save(d/'result.json',changed)
                with self.assertRaises(RuntimeError):c.verify_response(d,request,changed)

    def test_exclusive_write_and_owner_lock(self):
        with tempfile.TemporaryDirectory() as d,patch.object(c,'ROOT',Path(d)/'new'),patch.object(c.q,'ROOT',Path(d)):
            c.ROOT.mkdir();p=c.ROOT/'once.json';c.once(p,{'x':1})
            with self.assertRaises(FileExistsError):c.once(p,{'x':2})
            with c.ownership():
                with self.assertRaises(BlockingIOError):
                    with c.ownership():pass


if __name__=='__main__':unittest.main()
