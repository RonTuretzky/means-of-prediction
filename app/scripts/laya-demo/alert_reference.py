"""Frozen Google Alerts student-base reference; offline inference, never training.

freeze writes the candidate/profile/weights/token commitments BEFORE any forward.
run validates them, executes the complete stock CPU float32 model, and records
independent A/B flags. This is not an integer runtime or execution certificate.
"""
import argparse
import collections
import datetime as dt
from decimal import Decimal
import email
import email.policy
import hashlib
import importlib.metadata
import json
import os
import shutil
from pathlib import Path
import sys
import time

from artifacts import file_sha, pin_checkpoint, q6_layernorm, save, sha

HERE = Path(__file__).resolve().parent
BLIND = HERE.parent / 'research/blind'
sys.path.insert(0, str(BLIND))
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
MODEL = Path('/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/student-base')
WEIGHTS = '5ed8ce354cb1bf9f313fb4791f74601acbf955598d74f8d6742da3497aee5169'
FINAL_CONFIG = 'c388a2873fe58de011fbe58a27f6553a713f15f8c613c829227097bd2a6332ec'
RAW_CONFIG = 'a83b7896bfda813a7a2e7e602ab0fe04d6f61919e71e8dc31f3002dd41b6c7d9'
TEMPERATURE = 1.1089085340499878


def derive(candidate):
    import alerts_email
    import alerts_student
    raw = Path(candidate['raw']['path']).read_bytes()
    assert sha(raw) == candidate['raw']['sha256']
    parsed = alerts_email.parse(raw)
    unit = parsed['results'][candidate['exactUnit']['resultIndex']]
    for k, ck in [('headline','headline'), ('publisher','publisherLabel'), ('snippet','snippet'),
                  ('url','linkedURL'), ('host','linkedHost'), ('section','section')]:
        assert unit[k] == candidate['exactUnit'][ck], 'Changed unit: ' + k
    assert unit['host'] == candidate['market']['officialSourceHost']
    assert sha(candidate['market']['fullRules'].encode()) == candidate['market']['rulesSHA256']
    assert candidate['preInferenceExpected']['independentOfModelOutput']
    state = alerts_student.unit_state(unit)
    rule = {'factualA':candidate['preInferenceExpected']['A'],
            'factualB':candidate['preInferenceExpected']['B']}
    questions = alerts_student.questions(candidate['market']['question'], rule)
    assert list(questions) == ['q','A','B']
    # The Subject/query never enters state; "subject" is the extracted result headline.
    return unit, state, questions


def versions():
    return {n:importlib.metadata.version(n) for n in
            ['torch','transformers','laya','safetensors','tokenizers','numpy','dkimpy']}


def freeze(candidate_path, out):
    import alerts_email, alerts_student, laya_distill
    import laya.agent as agent_module
    import laya.common as common
    from transformers import AutoTokenizer
    from transformers.models.modernbert import modeling_modernbert
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    assert not (out/'frozen.private.json').exists(), 'Freeze is write-once'
    candidate = json.loads(candidate_path.read_bytes())
    unit, state, questions = derive(candidate)
    cfg = json.loads((MODEL/'rl_agent_config.json').read_bytes())
    assert file_sha(MODEL/'rl_agent_config.json') == FINAL_CONFIG
    assert file_sha(MODEL/'checkpoint_epoch1/rl_agent_config.json') == RAW_CONFIG
    assert cfg['temperature_by_options']['noul:2'] == TEMPERATURE
    assert cfg['max_len'] == 320 and cfg['head_max_len'] == 160
    pins = pin_checkpoint(MODEL)
    assert pins['weightsSha256'] == WEIGHTS
    raw_weight_hash = file_sha(MODEL/'checkpoint_epoch1/model.safetensors')
    assert raw_weight_hash == WEIGHTS
    # Agent normally rewrites tokenizer metadata in place. Preserve the source model:
    # perform exactly its compatibility transform on a private copy before freezing.
    # Weight bytes and calibration are unchanged; both metadata versions are pinned.
    runtime = out/'runtime-model'
    runtime.mkdir(mode=0o700)
    for folder in ['encoder','tokenizer']:shutil.copytree(MODEL/folder,runtime/folder)
    shutil.copy2(MODEL/'rl_agent_config.json',runtime/'rl_agent_config.json')
    (runtime/'model.safetensors').symlink_to(MODEL/'model.safetensors')
    agent_module._fix_tokenizer_config(str(runtime))
    tcfg=json.loads((runtime/'tokenizer/tokenizer_config.json').read_bytes())
    assert tcfg.get('tokenizer_class')=='PreTrainedTokenizerFast'
    assert not isinstance(tcfg.get('extra_special_tokens'),list)
    runtime_files={rel:file_sha(runtime/rel) for rel in pins['smallFilesSha256']}
    changed=[rel for rel,h in runtime_files.items() if h!=pins['smallFilesSha256'][rel]]
    assert changed==['tokenizer/tokenizer_config.json'],changed
    pins.update(runtimePath=str(runtime),runtimeSmallFilesSha256=runtime_files,
        compatibilityTransform={'function':'laya.agent._fix_tokenizer_config',
            'sourceSHA256':file_sha(agent_module.__file__),'changedFiles':changed,
            'purpose':'TokenizersBackend metadata to PreTrainedTokenizerFast; same tokenizer vocabulary/JSON, weights, calibration and templates'})
    save(out/'model-manifest.private.json', pins)
    tok = AutoTokenizer.from_pretrained(str(runtime/'tokenizer'), local_files_only=True)
    items=[]; untruncated=[]
    for qid, qdef in questions.items():
        q = agent_module.Agent._to_internal(qdef)
        ids, markers = common.build_sequence(tok,state,q,320,160)
        unc, _ = common.build_sequence(tok,state,q,4096,160)
        items.append({'ids':ids,'markers':markers,'qtype':common.QTYPES[q['t']]})
        untruncated.append({'question':qid,'length':len(unc),'retained':ids==unc})
    batch = common.collate_items([items],tok.pad_token_id)
    input_text = json.dumps({'state':state,'questions':questions},ensure_ascii=False,separators=(',',':'))
    input_bytes = input_text.encode()
    with (out/'input.private.json').open('xb') as fh: fh.write(input_bytes)
    tokens={'items':items,'batch':{k:v.tolist() for k,v in batch.items() if hasattr(v,'tolist')},
            'questionOrder':list(questions),'serializedState':common.serialize_state(state),
            'stateTokenIds':tok(common.serialize_state(state).replace(tok.mask_token,' '),add_special_tokens=False)['input_ids'],
            'untruncatedStateChecks':untruncated,'specialTokenIds':{
                'cls':tok.cls_token_id,'sep':tok.sep_token_id,'mask':tok.mask_token_id,'pad':tok.pad_token_id}}
    save(out/'tokens.private.json',tokens)
    modules=[alerts_email,alerts_student,laya_distill,agent_module,common,modeling_modernbert,email,email.policy]
    sources={str(Path(m.__file__).resolve()):file_sha(m.__file__) for m in modules}
    for p in [Path(__file__),HERE/'artifacts.py']:
        sources[str(p.resolve())]=file_sha(p)
    evidence_review=Path(candidate['reviewRecord'])
    handoff=HERE.parents[2]/'docs/HANDOFF-ALERT-STUDENT-20261021.md'
    aggregate=MODEL.parent/'eval-student-base-checkpoint_epoch1.json'
    frozen={'schema':2,'frozenBeforeInferenceAtUTC':dt.datetime.now(dt.UTC).isoformat(),
        'candidatePath':str(candidate_path),'candidateSHA256':file_sha(candidate_path),
        'raw':candidate['raw'],'market':candidate['market'],'exactUnit':unit,'state':state,'questions':questions,
        'preInferenceExpected':candidate['preInferenceExpected'],
        'profile':{'id':'alert-student-base-final-support-v1','modelPath':str(MODEL),'weightsSHA256':WEIGHTS,
            'configSHA256':FINAL_CONFIG,'maxLength':320,'headMaxLength':160,'temperatureNoul2':TEMPERATURE,
            'thresholdPpm':550000,'semantics':'independent rounded pA>=0.55 and pB>=0.55; no exclusive pick',
            'questionOrder':['q','A','B'],'qIsDiagnosticOnly':True,'headMaxTokensCombined':960,
            'selectionReason':'Handoff explicitly recommends final student-base with fitted temperatures; frozen before forward, no tuning.',
            'rawEpochWeightsSHA256':raw_weight_hash,'rawEpochConfigSHA256':RAW_CONFIG,
            'rawEpochTemperatureNoul2':json.loads((MODEL/'checkpoint_epoch1/rl_agent_config.json').read_bytes())['temperature_by_options']['noul:2'],
            'evaluationAttributionGate':'Existing aggregate evaluation names raw epoch with a different temperature; its quality/calibration is not established for final-root profile.',
            'handoffPath':str(handoff),'handoffSHA256':file_sha(handoff),
            'aggregateEvaluationPath':str(aggregate),'aggregateEvaluationSHA256':file_sha(aggregate)},
        'modelManifestSHA256':file_sha(out/'model-manifest.private.json'),
        'tokensSHA256':file_sha(out/'tokens.private.json'),'inputSHA256':sha(input_bytes),
        'sourceSHA256':sources,'packages':versions(),'python':sys.version,
        'priorAuthentication':{'reviewPath':str(evidence_review),'reviewSHA256':file_sha(evidence_review),
            'storedCandidateAuthentication':candidate['authentication'],'reverifiedNow':False,
            'limit':'Stored complete-body DKIM evidence only. No fresh DNS or historical-key proof claimed.'},
        'timing':candidate['timing'],'onchainExecution':False,'cryptographicInferenceProof':False}
    save(out/'frozen.private.json',frozen)
    digest=file_sha(out/'frozen.private.json')
    with (out/'frozen.sha256').open('x') as fh:fh.write(digest+'\n')
    print(json.dumps({'stage':'frozen-before-forward','pid':os.getpid(),'frozenSHA256':digest,
        'weightsSHA256':WEIGHTS,'profile':frozen['profile']['id'],'temperature':TEMPERATURE,
        'tokenLengths':[len(x['ids']) for x in items],'stateRetained':all(x['retained'] for x in untruncated)}),flush=True)


def run(out, threads):
    import numpy as np
    import torch
    import laya.agent as agent_module
    import laya.common as common
    frozen_path=out/'frozen.private.json'; f=json.loads(frozen_path.read_bytes())
    assert file_sha(frozen_path)==(out/'frozen.sha256').read_text().strip()
    assert file_sha(f['candidatePath'])==f['candidateSHA256']
    for p,h in f['sourceSHA256'].items(): assert file_sha(p)==h, 'Source drift: '+p
    assert versions()==f['packages'] and sys.version==f['python']
    for name,key in [('model-manifest.private.json','modelManifestSHA256'),
                     ('tokens.private.json','tokensSHA256'),('input.private.json','inputSHA256')]:
        assert file_sha(out/name)==f[key],name
    unit,state,questions=derive(json.loads(Path(f['candidatePath']).read_bytes()))
    assert (unit,state,questions)==(f['exactUnit'],f['state'],f['questions'])
    pins=json.loads((out/'model-manifest.private.json').read_bytes())
    assert file_sha(MODEL/'model.safetensors')==pins['weightsSha256']==WEIGHTS
    for rel,h in pins['smallFilesSha256'].items():assert file_sha(MODEL/rel)==h,rel
    profile=f['profile']; assert profile['temperatureNoul2']==TEMPERATURE and profile['thresholdPpm']==550000
    torch.set_num_threads(threads);torch.manual_seed(0);torch.use_deterministic_algorithms(True)
    runtime=Path(pins['runtimePath'])
    assert (runtime/'model.safetensors').resolve()==(MODEL/'model.safetensors').resolve()
    for rel,h in pins['runtimeSmallFilesSha256'].items():assert file_sha(runtime/rel)==h,rel
    start=time.perf_counter();agent=agent_module.Agent(str(runtime),device='cpu');load_seconds=time.perf_counter()-start
    assert agent.device.type=='cpu' and agent.dtype==torch.float32
    assert agent.temperature_by_options['noul:2']==TEMPERATURE
    assert agent.cfg['max_len']==320 and agent.cfg['head_max_len']==160
    for rel,h in pins['smallFilesSha256'].items():assert file_sha(MODEL/rel)==h,'Loader mutated '+rel
    for rel,h in pins['runtimeSmallFilesSha256'].items():assert file_sha(runtime/rel)==h,'Loader mutated runtime '+rel
    tokens=json.loads((out/'tokens.private.json').read_bytes())
    items=[]
    for q in questions.values():
        qi=agent._to_internal(q)
        ids,markers=common.build_sequence(agent.tok,state,qi,320,160)
        items.append({'ids':ids,'markers':markers,'qtype':common.QTYPES[qi['t']]})
    assert items==tokens['items']
    batch=common.collate_items([items],agent.tok.pad_token_id)
    assert {k:v.tolist() for k,v in batch.items() if hasattr(v,'tolist')}==tokens['batch']
    cfg=agent.model.encoder.config
    assert cfg.num_hidden_layers==28 and len(agent.model.head.layers)==2
    counts=collections.Counter();raw_outputs=[];handles=[];norms=[]
    # No numerical replacement: hooks expose execution. Replay restores the stock fast path.
    torch.backends.mha.set_fastpath_enabled(False)
    def pre(m,args):
        for key,t in zip(['input_ids','attention_mask','marker_pos','marker_mask','qtype'],args):
            assert torch.equal(t.cpu(),batch[key]),'Unbound tensor '+key
    handles.append(agent.model.register_forward_pre_hook(pre))
    for name,module in agent.model.named_modules():
        if ((name.startswith('encoder.layers.') or name.startswith('head.layers.')) and name.count('.')==2):
            handles.append(module.register_forward_hook(lambda m,i,o,n=name:counts.update([n])))
        if isinstance(module,torch.nn.LayerNorm) and name.startswith('encoder.'):
            def norm_hook(m,i,o,n=name):
                if norms:return
                x=i[0][0,0].detach().cpu().double();g=m.weight.detach().cpu().double();y=o[0,0].detach().cpu().double()
                assert m.bias is None and m.eps==1e-5
                xq=torch.round(x*1e6).to(torch.int64).tolist();gq=torch.round(g*1e6).to(torch.int64).tolist()
                yq=torch.round(y*1e6).to(torch.int64).tolist();exact=q6_layernorm(xq,gq)
                norm={'schema':1,'module':n,'frozenSHA256':file_sha(frozen_path),'weightsSha256':WEIGHTS,
                    'xQ6':xq,'gammaQ6':gq,'expectedQ6':exact,'floatOriginalQ6':yq,
                    'quantization':'Q6 ties-even inputs/gamma; variance floor; integer sqrt; signed division toward zero',
                    'maxErrorAgainstFloatQ6':max(abs(a-b) for a,b in zip(exact,yq))}
                save(out/'real-layernorm.private.json',norm);norms.append(norm)
            handles.append(module.register_forward_hook(norm_hook))
    handles.append(agent.model.register_forward_hook(lambda m,i,o:raw_outputs.append([v.detach().cpu().tolist() for v in o])))
    print(json.dumps({'stage':'model-loaded','pid':os.getpid(),'loadSeconds':load_seconds}),flush=True)
    start=time.perf_counter();answer=agent.system_one(state,questions);seconds=time.perf_counter()-start
    for h in handles:h.remove()
    assert len(counts)==30 and all(v==1 for v in counts.values())
    assert len(raw_outputs)==1 and norms
    probs={}
    for key,row in zip(questions,raw_outputs[0][0]):
        z=np.asarray(row,dtype=np.float32)/TEMPERATURE;p=np.exp(z-z.max());p/=p.sum()
        probs[key]=round(float(p[1]),4)
        assert probs[key]==answer['answers'][key]['noul']
    ppm={key:int(Decimal(str(probs[key]))*1000000) for key in ['A','B']}
    flags={key:ppm[key]>=550000 for key in ['A','B']}
    # Untouched stock run on the same loaded model, with no hooks or fastpath override.
    torch.backends.mha.set_fastpath_enabled(True)
    start=time.perf_counter();replay=agent.system_one(state,questions);replay_seconds=time.perf_counter()-start
    matched=replay==answer
    expected=f['preInferenceExpected']['label']
    result={'schema':2,'completedAtUTC':dt.datetime.now(dt.UTC).isoformat(),'pid':os.getpid(),
        'frozenSHA256':file_sha(frozen_path),'inputSHA256':f['inputSHA256'],'tokensSHA256':f['tokensSHA256'],
        'modelManifestSHA256':f['modelManifestSHA256'],'weightsSHA256':WEIGHTS,'profile':profile,
        'answer':answer,'probabilities':probs,'scoresPpm':ppm,'supportFlags':flags,
        'independentExpectedLabel':expected,'expectedSupportFlagsMatched':flags=={'A':True,'B':False},
        'stockReplay':replay,'stockReplayExactMatch':matched,'capturedLogitsAndActionLogits':raw_outputs[0],
        'executedLayers':dict(counts),'layerCount':len(counts),
        'resource':{'loadSeconds':load_seconds,'inferenceSeconds':seconds,'replaySeconds':replay_seconds,
            'threads':threads,'device':'cpu','dtype':'float32','sequenceLengths':[len(x['ids']) for x in items],
            'paddedSequenceLength':batch['input_ids'].shape[1],'batch':3},
        'packages':versions(),'onchainExecution':False,'cryptographicInferenceProof':False,
        'historicalKeyValidityEstablished':False,'prospectiveEvidence':False,
        'remainingGates':['authenticated body-to-article extraction and canonical tokenization',
            'complete deterministic integer model and full-model parity',
            'full Solidity model plus GasKiller authenticated request-bound execution result',
            'consumer source/timing/conflict policy and settlement/redemption',
            'final-root calibration quality attribution']}
    save(out/'reference-result.private.json',result)
    print(json.dumps({'stage':'complete-float-reference','pid':os.getpid(),'probabilities':probs,
        'supportFlags':flags,'independentExpected':expected,'expectedMatched':result['expectedSupportFlagsMatched'],
        'layers':len(counts),'stockReplayExactMatch':matched,'seconds':seconds,
        'fullIntegerOrOnchainExecution':False}),flush=True)
    assert matched,'Stock replay differs; recorded outputs, no result concealed'


if __name__=='__main__':
    os.umask(0o077)
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['freeze','run'])
    p.add_argument('--out',required=True,type=Path);p.add_argument('--candidate',type=Path)
    p.add_argument('--threads',type=int,default=4);a=p.parse_args()
    if a.stage=='freeze':
        assert a.candidate is not None
        freeze(a.candidate.resolve(),a.out.resolve())
    else:run(a.out.resolve(),a.threads)
