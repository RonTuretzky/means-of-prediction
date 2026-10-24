"""Fixed four-report Peace evidence/input freeze and unchanged full float reference.

Policy is pinned before forward. Every original field is retained; no model input
is concatenated or selected by model score. Old BBC artifacts remain immutable.
"""
import argparse
import collections
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
sys.dont_write_bytecode=True
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'research/blind'))
BASE=Path.home()/'.local/share/means-of-prediction'
OUT=BASE/'peace-four-report-demo-20261021'
OLD=BASE/'peace-demo-20261021'
REF=BASE/'laya-alert-demo-20261021/reference'
POLICY=BASE/'peace-source-admission-20261021/source-policy-frozen.private.json'
POLICY_SHA='464871658b2543c7cfd2fac61ecaf84ec32e437a06265dd12e648ea2750ea3a2'
OLD_SHA='b546ccf88a8d95b6f6a2183f249d60c0b7d764bd109235babae42cc19cf745d6'
MANIFEST_SHA='9d0153f9b6d7b940ba0e934b988ceeb695344ff9f233547e8a960b2394cdd13a'
WINDOWS_SHA='c0d902f9a634e7e9e025c6ab8ce22a3896e5d0c9f3f9dde3902dcd3dd0d6368c'
ORDER=['bbc','cnn','abc','rfi']


def file_sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def save(path,value):
    with path.open('x') as f:json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n')
    path.chmod(0o600)


def packages():
    return {n:importlib.metadata.version(n) for n in ['torch','transformers','laya','safetensors','tokenizers','numpy','dkimpy']}


def pins(manifest):
    model,runtime=Path(manifest['path']),Path(manifest['runtimePath'])
    assert file_sha(model/'model.safetensors')==manifest['weightsSha256']
    for base,values in [(model,manifest['smallFilesSha256']),(runtime,manifest['runtimeSmallFilesSha256'])]:
        for rel,digest in values.items():assert file_sha(base/rel)==digest,str(base/rel)
    assert (runtime/'model.safetensors').resolve()==(model/'model.safetensors').resolve()
    assert manifest['compatibilityTransform']['changedFiles']==['tokenizer/tokenizer_config.json']
    return runtime


def freeze(out):
    import alerts_email
    import alerts_student
    import laya.agent as am
    import laya.common as common
    import peace_four_report_input_binding as binding
    from transformers import AutoTokenizer
    from transformers.models.modernbert import modeling_modernbert
    start=time.perf_counter()
    out.mkdir(parents=True,mode=0o700,exist_ok=True)
    assert not (out/'frozen.private.json').exists(),'write-once freeze'
    assert file_sha(POLICY)==POLICY_SHA
    policy=json.loads(POLICY.read_text())
    assert policy['sourceOrder']==ORDER and policy['noNewScoresBeforeFreeze'] is True
    assert file_sha(OLD/'frozen.private.json')==OLD_SHA
    old=json.loads((OLD/'frozen.private.json').read_text())
    profile=old['profile']
    assert profile['thresholdPpm']==550000 and profile['temperatureNoul2']==1.1089085340499878
    assert profile['maxLength']==320 and profile['headMaxLength']==160
    assert old['market']['fullRules']==policy['fullRules'] and old['market']['fullRulesSHA256']==policy['fullRulesSHA256']
    assert old['factualA']==policy['factualA'] and old['factualB']==policy['factualB']
    mp=REF/'model-manifest.private.json';assert file_sha(mp)==MANIFEST_SHA
    manifest=json.loads(mp.read_text());runtime=pins(manifest)
    sp=out/'selected-windows.private.json';assert file_sha(sp)==WINDOWS_SHA
    selected=json.loads(sp.read_text());assert list(selected)==ORDER
    tests=binding.adversarial(selected)
    tok=AutoTokenizer.from_pretrained(str(runtime/'tokenizer'),local_files_only=True)
    items=[];input_checks=[];preserved={str(POLICY):POLICY_SHA,str(OLD/'frozen.private.json'):OLD_SHA,str(mp):MANIFEST_SHA}
    for path,digest in old['sourcePins'].items():assert file_sha(path)==digest,path;preserved[path]=digest
    for n in ['tokens.private.json','bbc-input.private.json','reference-results.private.json','prior-baseline.private.json']:
        preserved[str(OLD/n)]=file_sha(OLD/n)
    for index,name in enumerate(ORDER):
        source=selected[name];report=policy['reports'][index];e=source['evidence']
        assert report['sourceKey']==name and report['result']==e['result'] and report['rawSHA256']==e['rawSHA256'] and report['unitSHA256']==e['unitSHA256']
        assert report['canonicalBodySHA256']==source['canonicalBodySha256'][2:] and report['bodyOffset']==source['bodyOffset'] and report['encodedLength']==source['encodedLength']
        audit=report['authenticationAudit'];assert file_sha(audit['path'])==audit['sha256'];preserved[audit['path']]=audit['sha256']
        unit,decoded=binding.bind_window(source)
        raw=Path(e['rawPath']).read_bytes();assert binding.sha(raw)==e['rawSHA256']
        assert alerts_email.parse(raw)['results'][report['resultIndex']]==unit
        state=alerts_student.unit_state(unit)
        questions=alerts_student.questions(old['question'],{'factualA':policy['factualA'],'factualB':policy['factualB']})
        assert list(state)==['subject','body'] and list(questions)==['q','A','B']
        tokens=[]
        for qid,qdef in questions.items():
            qi=am.Agent._to_internal(qdef);ids,markers=common.build_sequence(tok,state,qi,320,160);unc,_=common.build_sequence(tok,state,qi,4096,160)
            assert ids==unc,'unexpected sequence cropping: '+name
            tokens.append({'question':qid,'ids':ids,'markers':markers,'qtype':common.QTYPES[qi['t']],'stateRetained':True})
        internal=[{k:t[k] for k in ['ids','markers','qtype']} for t in tokens];batch=common.collate_items([internal],tok.pad_token_id);tensors={k:v.tolist() for k,v in batch.items() if hasattr(v,'tolist')}
        input_bytes=json.dumps({'state':state,'questions':questions},ensure_ascii=False,separators=(',',':')).encode();ip=out/(name+'-input.private.json')
        with ip.open('xb') as f:f.write(input_bytes)
        ip.chmod(0o600)
        flat=[v for t in tokens for v in t['ids']];gh=binding.gate_hashes(input_bytes,flat,Path.home()/'.foundry/bin/cast')
        item={'id':source['candidateID'],'sourceKey':name,'sourceGroup':report['reportingOrigin'],'sourceGroupIndex':index,'unitSHA256':e['unitSHA256'],'unit':unit,'state':state,'questions':questions,'tokens':tokens,'batch':tensors,'flatTokenIds':flat,'inputPath':str(ip),'inputSHA256':binding.sha(input_bytes),'inputBytes':len(input_bytes),'gateHashes':gh,'rawPath':e['rawPath'],'rawSHA256':e['rawSHA256'],'resultIndex':report['resultIndex'],'sourceEvidence':e,'signedAtUTC':e['signedAtUTC'],'window':{k:v for k,v in source.items() if k not in ['bodyHex','headerHex','decodedHex','encodedWindowHex','evidence','originalPolicyReport']},'expectedSupport':{'A':True,'B':False},'cropPolicy':{'function':'unchanged alerts_student.unit_state','headlineMaxChars':110,'snippetMaxChars':162,'originalSnippetCharacters':len(unit['snippet']),'modelSnippetCharacters':len(alerts_student.cut(unit['snippet'],162)),'sequenceMaxTokens':320,'headMaxTokens':160,'combinedMaxTokens':960,'allSequencesUncropped':True}}
        for t in binding.input_audit(item,tok,common,am):input_checks.append({'sourceKey':name,**t})
        if name=='bbc':
            oi=old['items'][0];assert input_bytes==Path(oi['inputPath']).read_bytes() and state==oi['state'] and questions==oi['questions'] and tokens==oi['tokens'] and tensors==oi['batch'] and gh==oi['gateHashes'],'old BBC parity'
        items.append(item)
    save(out/'tokens.private.json',{'questionOrder':['q','A','B'],'variants':[{k:i[k] for k in ['id','sourceKey','tokens','batch','flatTokenIds','inputPath','inputSHA256','gateHashes']} for i in items],'specialTokenIds':{'cls':tok.cls_token_id,'sep':tok.sep_token_id,'mask':tok.mask_token_id,'pad':tok.pad_token_id}})
    save(out/'extraction-checks.private.json',{'tests':tests,'allPassed':True,'count':len(tests),'scope':'Strict offline fixed four-field prefix grammar; no Solidity extraction or general tokenizer proof.'})
    save(out/'input-binding-audit.private.json',{'tests':input_checks,'allPassed':True,'count':len(input_checks),'gap':'Exact known-output policy commitments; no onchain HTML extraction/tokenizer execution.'})
    prior=json.loads((OLD/'prior-baseline.private.json').read_text())
    save(out/'prior-baseline.private.json',prior)
    # Byte-identical policy copy keeps original pre-score policy SHA stable.
    with (out/'source-policy.private.json').open('xb') as f:f.write(POLICY.read_bytes())
    (out/'source-policy.private.json').chmod(0o600)
    sources={str(Path(m.__file__).resolve()):file_sha(m.__file__) for m in [alerts_email,alerts_student,am,common,modeling_modernbert,binding]};sources[str(Path(__file__).resolve())]=file_sha(__file__)
    f={'schema':'peace-four-report-5371292-input-freeze-v1','frozenBeforeNewInferenceAtUTC':dt.datetime.now(dt.UTC).isoformat(),'preselectedOrder':ORDER,'market':old['market'],'fullRulesSHA256':policy['fullRulesSHA256'],'question':old['question'],'factualA':policy['factualA'],'factualB':policy['factualB'],'profile':profile,'profileSHA256':old['profileSHA256'],'modelManifestPath':str(mp),'modelManifestSHA256':MANIFEST_SHA,'packages':packages(),'python':sys.version,'sourcePins':sources,'preservedOldArtifacts':preserved,'items':items,'sourcePolicy':policy,'sourcePolicyPath':str(POLICY),'sourcePolicySHA256':POLICY_SHA,'selectedWindowsPath':str(sp),'selectedWindowsSHA256':WINDOWS_SHA,'tokensSHA256':file_sha(out/'tokens.private.json'),'extractionChecksSHA256':file_sha(out/'extraction-checks.private.json'),'inputBindingAuditSHA256':file_sha(out/'input-binding-audit.private.json'),'priorBaselineSHA256':file_sha(out/'prior-baseline.private.json'),'priorBBCExactInputTokensBatchHashesPreserved':True,'noNewForwardBeforeThisFreeze':True,'freezeSeconds':time.perf_counter()-start,'scope':'Fixed qualitative rule-source fallback packet chosen before scores. Complete CPU float reference/offline deterministic extraction/tokenization, not settlement or onchain model/extraction proof.'}
    save(out/'frozen.private.json',f)
    (out/'frozen.sha256').write_text(file_sha(out/'frozen.private.json')+'\n');(out/'frozen.sha256').chmod(0o600)
    print(json.dumps({'stage':'frozen-before-forward','frozenSHA256':file_sha(out/'frozen.private.json'),'tokensSHA256':f['tokensSHA256'],'sourcePolicySHA256':POLICY_SHA,'windowSHA256':WINDOWS_SHA,'variants':[{'sourceKey':i['sourceKey'],'tokens':[len(t['ids']) for t in i['tokens']],'inputSHA256':i['inputSHA256'],'gateHashes':{k:v for k,v in i['gateHashes'].items() if k!='tokenIdsABIHex'}} for i in items],'extractionChecks':len(tests),'inputChecks':len(input_checks),'bbcExactParity':True}),flush=True)


def validate(out):
    f=json.loads((out/'frozen.private.json').read_text());assert file_sha(out/'frozen.private.json')==(out/'frozen.sha256').read_text().strip()
    for path,digest in f['sourcePins'].items():assert file_sha(path)==digest,path
    for path,digest in f['preservedOldArtifacts'].items():assert file_sha(path)==digest,path
    for n,k in [('tokens.private.json','tokensSHA256'),('extraction-checks.private.json','extractionChecksSHA256'),('input-binding-audit.private.json','inputBindingAuditSHA256'),('source-policy.private.json','sourcePolicySHA256'),('prior-baseline.private.json','priorBaselineSHA256')]:assert file_sha(out/n)==f[k],n
    assert file_sha(f['sourcePolicyPath'])==f['sourcePolicySHA256'] and json.loads(Path(f['sourcePolicyPath']).read_text())==f['sourcePolicy']
    assert file_sha(f['selectedWindowsPath'])==f['selectedWindowsSHA256']
    assert packages()==f['packages'] and sys.version==f['python']
    manifest=json.loads(Path(f['modelManifestPath']).read_text());runtime=pins(manifest)
    for i in f['items']:assert file_sha(i['rawPath'])==i['rawSHA256'] and file_sha(i['inputPath'])==i['inputSHA256']
    return f,manifest,runtime


def run(out, threads):
    import torch
    import laya.agent as am
    import laya.common as common
    import peace_four_report_input_binding as binding
    assert not (out / 'inference-started.private.json').exists(), 'write-once run; no unreported reruns'
    f, manifest, runtime = validate(out)
    save(out / 'inference-started.private.json', {'atUTC':dt.datetime.now(dt.UTC).isoformat(),'frozenSHA256':file_sha(out / 'frozen.private.json'),'variants':ORDER,'passesPerVariant':'one instrumented full forward + one stock parity replay','pid':os.getpid()})
    torch.set_num_threads(threads)
    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True)
    start = time.perf_counter()
    agent = am.Agent(str(runtime), device='cpu')
    load_seconds = time.perf_counter() - start
    assert agent.dtype == torch.float32 and agent.device.type == 'cpu'
    assert agent.temperature_by_options['noul:2'] == f['profile']['temperatureNoul2']
    assert agent.cfg['max_len'] == 320 and agent.cfg['head_max_len'] == 160
    assert agent.model.encoder.config.num_hidden_layers == 28 and len(agent.model.head.layers) == 2
    print(json.dumps({'stage':'loaded','seconds':load_seconds,'pid':os.getpid()}),flush=True)
    results = []
    for item in f['items']:
        # Dict insertion order is semantically significant in Laya serialize_state.
        # Sorted-key manifest JSON retains values but not the original input order;
        # restore both dictionaries from the separately pinned exact input bytes.
        exact_input = json.loads(Path(item['inputPath']).read_bytes())
        assert exact_input['state'] == item['state'] and exact_input['questions'] == item['questions']
        item['state'], item['questions'] = exact_input['state'], exact_input['questions']
        assert list(item['state']) == ['subject', 'body'] and list(item['questions']) == ['q', 'A', 'B']
        name = item['sourceKey']
        verify_items = []
        for q in item['questions'].values():
            qi = agent._to_internal(q)
            ids, markers = common.build_sequence(agent.tok, item['state'], qi, 320, 160)
            verify_items.append({'ids':ids,'markers':markers,'qtype':common.QTYPES[qi['t']]})
        expected_items = [{k:t[k] for k in ['ids','markers','qtype']} for t in item['tokens']]
        assert verify_items == expected_items
        batch = common.collate_items([verify_items], agent.tok.pad_token_id)
        assert {k:v.tolist() for k,v in batch.items() if hasattr(v,'tolist')} == item['batch']
        counts = collections.Counter()
        tensors = {}
        raw_output = []
        handles = []
        def layer_hook(m, args, output, key):
            counts.update([key])
            v = output if isinstance(output, torch.Tensor) else output[0]
            tensors[key] = v.detach().cpu().clone()
        def model_pre(m,args):
            for key,v in zip(['input_ids','attention_mask','marker_pos','marker_mask','qtype'],args):
                assert torch.equal(v.cpu(),batch[key]), 'unbound tensor: ' + key
        handles.append(agent.model.register_forward_pre_hook(model_pre))
        for module_name, module in agent.model.named_modules():
            if (module_name.startswith('encoder.layers.') or module_name.startswith('head.layers.')) and module_name.count('.') == 2:
                handles.append(module.register_forward_hook(lambda m,i,o,n=module_name:layer_hook(m,i,o,n)))
        handles.append(agent.model.register_forward_hook(lambda m,i,o:raw_output.append([v.detach().cpu().clone() for v in o])))
        torch.backends.mha.set_fastpath_enabled(False)
        start = time.perf_counter()
        answer = agent.system_one(item['state'], item['questions'])
        seconds = time.perf_counter() - start
        for h in handles:
            h.remove()
        assert len(counts) == 30 and all(v == 1 for v in counts.values()) and len(raw_output) == 1
        tensor_path = out / (name + '-float-trace.private.pt')
        assert not tensor_path.exists()
        torch.save({'layers':tensors,'rawModelOutputs':raw_output[0],'boundBatch':batch,'questionOrder':['q','A','B'],'frozenSHA256':file_sha(out / 'frozen.private.json')}, tensor_path)
        tensor_path.chmod(0o600)
        torch.backends.mha.set_fastpath_enabled(True)
        start = time.perf_counter()
        replay = agent.system_one(item['state'], item['questions'])
        replay_seconds = time.perf_counter() - start
        probabilities = {k:answer['answers'][k]['noul'] for k in ['q','A','B']}
        flags = {k:probabilities[k] >= 0.55 for k in ['A','B']}
        record = {'sourceKey':name,'candidateID':item['id'],'probabilities':probabilities,'flags':flags,'expectedFactualSnippetSupport':item['expectedSupport'],'matchesExpectedFactualSupport':flags == item['expectedSupport'],'stockReplayExact':replay == answer,'instrumentedSeconds':seconds,'stockReplaySeconds':replay_seconds,'layers':dict(counts),'answer':answer,'rawScoringLogits':raw_output[0][0].tolist(),'tracePath':str(tensor_path),'traceSHA256':file_sha(tensor_path),'layerShapes':{k:list(v.shape) for k,v in tensors.items()},'passes':{'instrumented':1,'stockReplay':1}}
        save(out / (name + '-result.private.json'), record)
        results.append(record)
        print(json.dumps({k:v for k,v in record.items() if k in ['sourceKey','probabilities','flags','matchesExpectedFactualSupport','stockReplayExact','instrumentedSeconds','stockReplaySeconds']}),flush=True)
        assert replay == answer, 'stock float parity failed; preserved result, no tuning'
        baseline=json.loads((out/'prior-baseline.private.json').read_text())['output']
        if name == 'bbc':
            assert answer==baseline['answer'], 'prior BBC result mismatch preserved; no tuning'
    validate(out)
    report = {'atUTC':dt.datetime.now(dt.UTC).isoformat(),'frozenSHA256':file_sha(out / 'frozen.private.json'),'profile':f['profile'],'loadSeconds':load_seconds,'outputs':results,'allStockParityExact':all(x['stockReplayExact'] for x in results),'noModelOrCalibrationChanges':True,'noTraining':True,'priorBaselinePreserved':True,'scope':'Stock full CPU float32,28encoder+2head. Not integer/certificate/onchain execution or settlement. All fixed four-report variants reported, including any abstention/conflict. Source-policy admission was pre-score; model flags remain independent. No EVM model or settlement claim.'}
    save(out / 'reference-results.private.json', report)
    print(json.dumps({'stage':'complete','resultsSHA256':file_sha(out / 'reference-results.private.json'),'allStockParityExact':report['allStockParityExact']}),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('stage',choices=['freeze','run']);ap.add_argument('--out',type=Path,default=OUT);ap.add_argument('--threads',type=int,default=4)
    args=ap.parse_args();os.umask(0o077)
    if args.stage=='freeze':freeze(args.out)
    else:run(args.out,args.threads)
