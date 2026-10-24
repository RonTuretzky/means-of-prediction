"""Write-once Peace BBC freeze and unchanged complete stock float reference.

Offline only. The exact prior BBC state/questions/tokens are reproduced before
forward. A-support is factual snippet support, not human source-policy admission.
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
OUT=BASE/'peace-demo-20261021'
OLD=BASE/'alerts-candidate-sweep-20261021'
REF=BASE/'laya-alert-demo-20261021/reference'
ORDER=['bbc']
ID='peace-individual-pillay-20261009-smaller-531c9380501e'
UNIT_SHA='531c9380501e31990f65ec0cda82026554eeaf10efaf960ca9cbbe574fe36a7c'


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
    import peace_input_binding as binding
    from transformers import AutoTokenizer
    from transformers.models.modernbert import modeling_modernbert
    start=time.perf_counter()
    out.mkdir(parents=True,mode=0o700,exist_ok=True)
    assert not (out/'frozen.private.json').exists(),'write-once freeze'
    docs={};inputs={}
    for name,(path,digest) in binding.PINS.items():
        assert file_sha(path)==digest,name
        docs[name]=json.loads(path.read_text());inputs[str(path)]=digest
    old=next(x for x in docs['frozen']['items'] if x['id']==ID)
    selection=next(x for x in docs['selection']['candidates'] if x['id']==ID)
    source=docs['fixture']['sources']['bbc']
    assert selection['market']['id']=='5371292'
    assert hashlib.sha256(selection['market']['fullRules'].encode()).hexdigest()==selection['market']['fullRulesSHA256']
    assert old['expectedSupport']=={'A':True,'B':False}
    profile=docs['frozen']['profile']
    assert profile==docs['priorFrozen']['profile'] and profile['thresholdPpm']==550000
    assert profile['temperatureNoul2']==1.1089085340499878 and profile['maxLength']==320 and profile['headMaxLength']==160
    runtime=pins(docs['manifest'])
    unit,decoded=binding.bind_source(source,old)
    raw=Path(old['rawPath']).read_bytes()
    assert binding.sha(raw)==old['rawSHA256']
    assert alerts_email.parse(raw)['results'][old['resultIndex']]==unit
    state=alerts_student.unit_state(unit)
    questions=alerts_student.questions(selection['market']['question'],{'factualA':selection['factualA'],'factualB':selection['factualB']})
    assert state==old['state']==source['modelState'] and questions==old['questions']==source['modelQuestions']
    assert list(state)==['subject','body'] and list(questions)==['q','A','B']
    tok=AutoTokenizer.from_pretrained(str(runtime/'tokenizer'),local_files_only=True)
    tokens=[]
    for qid,qdef in questions.items():
        qi=am.Agent._to_internal(qdef)
        ids,markers=common.build_sequence(tok,state,qi,320,160)
        unc,_=common.build_sequence(tok,state,qi,4096,160)
        assert ids==unc,'unexpected sequence cropping'
        tokens.append({'question':qid,'ids':ids,'markers':markers,'qtype':common.QTYPES[qi['t']],'stateRetained':True})
    assert tokens==old['tokens'],'prior exact token parity'
    batch=common.collate_items([[{k:t[k] for k in ['ids','markers','qtype']} for t in tokens]],tok.pad_token_id)
    tensors={k:v.tolist() for k,v in batch.items() if hasattr(v,'tolist')}
    input_bytes=json.dumps({'state':state,'questions':questions},ensure_ascii=False,separators=(',',':')).encode()
    ip=out/'bbc-input.private.json'
    with ip.open('xb') as f:f.write(input_bytes)
    ip.chmod(0o600)
    flat=[v for t in tokens for v in t['ids']]
    gate_hashes=binding.gate_hashes(input_bytes,flat,Path.home()/'.foundry/bin/cast')
    item={'id':ID,'sourceKey':'bbc','sourceGroup':'BBC','sourceGroupIndex':0,'unitSHA256':UNIT_SHA,'unit':unit,'state':state,'questions':questions,'tokens':tokens,'batch':tensors,'flatTokenIds':flat,'inputPath':str(ip),'inputSHA256':binding.sha(input_bytes),'inputBytes':len(input_bytes),'gateHashes':gate_hashes,'rawPath':old['rawPath'],'rawSHA256':old['rawSHA256'],'resultIndex':old['resultIndex'],'sourceEvidence':selection,'signedAtUTC':selection['signedAtUTC'],'window':{k:v for k,v in source.items() if k not in ['bodyHex','headerHex','decodedHex','modelState','modelQuestions']},'expectedSupport':{'A':True,'B':False},'expectedSupportConditionalOnAdmittedPair':{'A':True,'B':False},'cropPolicy':{'function':'unchanged alerts_student.unit_state','headlineMaxChars':110,'snippetMaxChars':162,'originalSnippetCharacters':len(unit['snippet']),'modelSnippetCharacters':len(alerts_student.cut(unit['snippet'],162)),'sequenceMaxTokens':320,'headMaxTokens':160,'combinedMaxTokens':960,'allSequencesUncropped':True}}
    checks=binding.adversarial(source,old)
    audits=binding.input_audit(item,tok,common,am)
    prior_path=OLD/'shortlist-results.private.json'
    prior=json.loads(prior_path.read_text())
    prior_output=next(x for x in prior['outputs'] if x['id']==ID)
    assert prior_output['probabilities']=={'q':0.8828,'A':0.8931,'B':0.0529}
    save(out/'prior-baseline.private.json',{'path':str(prior_path),'sha256':file_sha(prior_path),'output':prior_output,'immutable':True})
    save(out/'selected-windows.private.json',{'bbc':source})
    save(out/'tokens.private.json',{'questionOrder':['q','A','B'],'variants':[{k:item[k] for k in ['id','sourceKey','tokens','batch','flatTokenIds','inputPath','inputSHA256','gateHashes']}],'specialTokenIds':{'cls':tok.cls_token_id,'sep':tok.sep_token_id,'mask':tok.mask_token_id,'pad':tok.pad_token_id}})
    save(out/'extraction-checks.private.json',{'tests':checks,'allPassed':True,'count':len(checks),'scope':'Strict offline oneArticle four-field grammar; no onchain extraction or general tokenizer proof.'})
    save(out/'input-binding-audit.private.json',{'tests':audits,'allPassed':True,'count':len(audits),'gap':'Hashes policy-pin exact known output; Solidity does not execute HTML extraction or tokenizer.'})
    policy={'schema':'peace-bbc-observation-source-policy-v1','marketId':5371292,'primary':'First official Norwegian Nobel Committee announcement at nobelprize.org. This BBC Audio profile is not that primary source.','fallback':'A consensus of credible reporting may be used; one BBC report does not establish consensus by itself.','humanExpectedFactualSupport':{'A':True,'B':False},'humanSourceAdmission':False,'distinctReportingGroups':['BBC'],'unresolvedPredicates':['First official announcement has not been admitted for this exact fixture.','Credible-reporting consensus is not established by single BBC source.','Google signed relay bytes are not publisher authorship or truth proof.','No prospective protocol acceptance or actual market settlement demonstrated.'],'timing':'BBC signed Oct18; earlier Reuters/AP DKIM expiry Oct17 precedes BBC signature. No common signature-valid time window for those three sources. No historical-clock loophole or source substitution.'}
    save(out/'source-policy.private.json',policy)
    source_pins={str(Path(m.__file__).resolve()):file_sha(m.__file__) for m in [alerts_email,alerts_student,am,common,modeling_modernbert,binding]}
    source_pins[str(Path(__file__).resolve())]=file_sha(__file__)
    frozen={'schema':'peace-5371292-bbc-input-freeze-v1','frozenBeforeNewInferenceAtUTC':dt.datetime.now(dt.UTC).isoformat(),'preselectedOrder':ORDER,'market':selection['market'],'question':selection['market']['question'],'factualA':selection['factualA'],'factualB':selection['factualB'],'profile':profile,'profileSHA256':hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'modelManifestPath':str(binding.PINS['manifest'][0]),'modelManifestSHA256':binding.PINS['manifest'][1],'packages':packages(),'python':sys.version,'sourcePins':source_pins,'preservedOldArtifacts':inputs|{str(prior_path):file_sha(prior_path)},'items':[item],'priorBaselineID':ID,'priorBaselineInputExactParity':True,'priorBaselinePreserved':True,'noNewForwardBeforeThisFreeze':True,'sourcePolicy':policy,'sourcePolicySHA256':file_sha(out/'source-policy.private.json'),'tokensSHA256':file_sha(out/'tokens.private.json'),'selectedWindowsPath':str(out/'selected-windows.private.json'),'selectedWindowsSHA256':file_sha(out/'selected-windows.private.json'),'extractionChecksSHA256':file_sha(out/'extraction-checks.private.json'),'inputBindingAuditSHA256':file_sha(out/'input-binding-audit.private.json'),'priorBaselineSHA256':file_sha(out/'prior-baseline.private.json'),'freezeSeconds':time.perf_counter()-start,'scope':'Offline deterministic extraction/tokenization and CPU float reference. No consensus admission, certificate, onchain inference or settlement claim.'}
    save(out/'frozen.private.json',frozen)
    (out/'frozen.sha256').write_text(file_sha(out/'frozen.private.json')+'\n');(out/'frozen.sha256').chmod(0o600)
    print(json.dumps({'stage':'frozen-before-forward','frozenSHA256':file_sha(out/'frozen.private.json'),'profileSHA256':frozen['profileSHA256'],'tokensSHA256':frozen['tokensSHA256'],'sourcePolicySHA256':frozen['sourcePolicySHA256'],'tokenCounts':[len(t['ids']) for t in tokens],'combinedTokens':len(flat),'inputBytes':len(input_bytes),'gateHashes':{k:v for k,v in gate_hashes.items() if k!='tokenIdsABIHex'},'extractionChecks':len(checks),'inputChecks':len(audits),'freezeSeconds':frozen['freezeSeconds']}),flush=True)


def validate(out):
    f=json.loads((out/'frozen.private.json').read_text())
    assert file_sha(out/'frozen.private.json')==(out/'frozen.sha256').read_text().strip()
    for path,digest in f['sourcePins'].items():assert file_sha(path)==digest,path
    for path,digest in f['preservedOldArtifacts'].items():assert file_sha(path)==digest,path
    for name,key in [('tokens.private.json','tokensSHA256'),('extraction-checks.private.json','extractionChecksSHA256'),('input-binding-audit.private.json','inputBindingAuditSHA256'),('source-policy.private.json','sourcePolicySHA256'),('prior-baseline.private.json','priorBaselineSHA256')]:assert file_sha(out/name)==f[key],name
    assert file_sha(f['selectedWindowsPath'])==f['selectedWindowsSHA256']
    assert packages()==f['packages'] and sys.version==f['python']
    manifest=json.loads(Path(f['modelManifestPath']).read_text());runtime=pins(manifest)
    for i in f['items']:assert file_sha(i['rawPath'])==i['rawSHA256'] and file_sha(i['inputPath'])==i['inputSHA256']
    return f,manifest,runtime


def run(out, threads):
    import torch
    import laya.agent as am
    import laya.common as common
    import peace_input_binding as binding
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
        assert answer==baseline['answer'], 'prior BBC result mismatch preserved; no tuning'
    validate(out)
    report = {'atUTC':dt.datetime.now(dt.UTC).isoformat(),'frozenSHA256':file_sha(out / 'frozen.private.json'),'profile':f['profile'],'loadSeconds':load_seconds,'outputs':results,'allStockParityExact':all(x['stockReplayExact'] for x in results),'noModelOrCalibrationChanges':True,'noTraining':True,'priorBaselinePreserved':True,'scope':'Stock full CPU float32,28encoder+2head. Not integer/certificate/onchain execution or settlement. Single BBC original variant; factual A does not establish source consensus or settlement.'}
    save(out / 'reference-results.private.json', report)
    print(json.dumps({'stage':'complete','resultsSHA256':file_sha(out / 'reference-results.private.json'),'allStockParityExact':report['allStockParityExact']}),flush=True)


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stage',choices=['freeze','run'])
    ap.add_argument('--out',type=Path,default=OUT)
    ap.add_argument('--threads',type=int,default=4)
    args=ap.parse_args();os.umask(0o077)
    if args.stage=='freeze':freeze(args.out)
    else:run(args.out,args.threads)
