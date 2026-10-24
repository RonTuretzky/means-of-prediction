"""Write-once Chemistry evidence/input freeze and unchanged stock float reference.

freeze derives all preselected original windows and q/A/B tokens before any new
forward. run executes each frozen variant once instrumented plus one stock parity
replay. No training, model selection, prompt tuning, calibration, or settlement.
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

sys.dont_write_bytecode = True
os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'research/blind'))
BASE = Path.home() / '.local/share/means-of-prediction'
OUT = BASE / 'chemistry-demo-20261021'
SWEEP = BASE / 'alerts-notability-sweep-20261021'
OLD = BASE / 'alerts-candidate-sweep-20261021'
REF = BASE / 'laya-alert-demo-20261021/reference'
RANKING_SHA = 'c777a922ad9ecc50acfe098e8bf946f289b4ec351a22642f2b3e2cd8f27a4e78'
MANIFEST_SHA = '9d0153f9b6d7b940ba0e934b988ceeb695344ff9f233547e8a960b2394cdd13a'
QUESTION = 'Will Takuzo Aida win the Nobel Prize in Chemistry in 2026?'
A = 'Takuzo Aida was named a laureate of the 2026 Nobel Prize in Chemistry.'
B = 'Takuzo Aida was not among the announced laureates of the 2026 Nobel Prize in Chemistry.'
ORDER = ['reuters_early', 'ap', 'reuters_later']


def file_sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write('\n')
    path.chmod(0o600)


def packages():
    return {n: importlib.metadata.version(n) for n in ['torch', 'transformers', 'laya', 'safetensors', 'tokenizers', 'numpy', 'dkimpy']}


def pins(manifest):
    model, runtime = Path(manifest['path']), Path(manifest['runtimePath'])
    assert file_sha(model / 'model.safetensors') == manifest['weightsSha256']
    for base, values in [(model, manifest['smallFilesSha256']), (runtime, manifest['runtimeSmallFilesSha256'])]:
        for rel, digest in values.items():
            assert file_sha(base / rel) == digest, str(base / rel)
    assert (runtime / 'model.safetensors').resolve() == (model / 'model.safetensors').resolve()
    return runtime


def freeze(out):
    import alerts_email
    import alerts_student
    import laya.agent as am
    import laya.common as common
    from transformers import AutoTokenizer
    from transformers.models.modernbert import modeling_modernbert
    import chemistry_input_binding as binding
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    assert not (out / 'frozen.private.json').exists(), 'write-once freeze'
    ranking_path = SWEEP / 'ranked-shortlist-final-frozen.private.json'
    assert file_sha(ranking_path) == RANKING_SHA
    selection = json.loads(ranking_path.read_text())['entries'][1]
    assert selection['market']['marketId'] == '5371179' and selection['market']['question'] == QUESTION
    assert hashlib.sha256(selection['market']['fullRules'].encode()).hexdigest() == selection['market']['fullRulesSha256']
    selected_path = out / 'selected-windows.private.json'
    selected = json.loads(selected_path.read_text())
    assert list(selected) == ORDER
    manifest_path = REF / 'model-manifest.private.json'
    assert file_sha(manifest_path) == MANIFEST_SHA
    manifest = json.loads(manifest_path.read_text())
    runtime = pins(manifest)
    prior = json.loads((REF / 'frozen.private.json').read_text())
    profile = prior['profile']
    assert profile['maxLength'] == 320 and profile['headMaxLength'] == 160 and profile['thresholdPpm'] == 550000
    assert profile['temperatureNoul2'] == 1.1089085340499878
    old_input = next(c for c in json.loads((OLD / 'shortlist.private.json').read_text())['candidates'] if c['rank'] == 16)
    assert old_input['factualA'] == A and old_input['factualB'] == B
    tests = binding.adversarial(selected)
    assert all(x['passed'] for x in tests)
    tok = AutoTokenizer.from_pretrained(str(runtime / 'tokenizer'), local_files_only=True)
    items = []
    for name in ORDER:
        source = selected[name]
        unit, decoded = binding.bind_window(source)
        e = source['evidence']
        raw = Path(e['rawPath']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == e['occurrence']['rawSHA256']
        assert alerts_email.parse(raw)['results'][e['occurrence']['resultIndex']] == unit
        state = alerts_student.unit_state(unit)
        questions = alerts_student.questions(QUESTION, {'factualA': A, 'factualB': B})
        assert list(questions) == ['q', 'A', 'B']
        tokens = []
        for qid, qdef in questions.items():
            qi = am.Agent._to_internal(qdef)
            ids, markers = common.build_sequence(tok, state, qi, 320, 160)
            unc, _ = common.build_sequence(tok, state, qi, 4096, 160)
            assert ids == unc, 'state cropped unexpectedly: ' + name
            tokens.append({'question': qid, 'ids': ids, 'markers': markers, 'qtype': common.QTYPES[qi['t']], 'stateRetained': True})
        internal_items = [{k: t[k] for k in ['ids', 'markers', 'qtype']} for t in tokens]
        batch = common.collate_items([internal_items], tok.pad_token_id)
        tensors = {k: v.tolist() for k, v in batch.items() if hasattr(v, 'tolist')}
        # This exact insertion order is the existing reference serialization, not
        # sorted-key JSON. The bytes themselves are separately persisted and pinned.
        input_bytes = json.dumps({'state': state, 'questions': questions}, ensure_ascii=False, separators=(',', ':')).encode()
        input_path = out / (name + '-input.private.json')
        with input_path.open('xb') as f:
            f.write(input_bytes)
        flat_ids = [i for t in tokens for i in t['ids']]
        gate_hashes = binding.gate_hashes(input_bytes, flat_ids, Path.home() / '.foundry/bin/cast')
        record = {'id': source['candidateID'], 'sourceKey': name, 'unitSHA256': e['unitSHA256'], 'rawPath': e['rawPath'], 'rawSHA256': e['occurrence']['rawSHA256'], 'resultIndex': e['occurrence']['resultIndex'], 'sourceGroup': 'AP' if name == 'ap' else 'Reuters', 'sourceGroupIndex': 1 if name == 'ap' else 0, 'signedAtUTC': e['signedAtUTC'], 'sourceEvidence': e, 'window': {k: v for k, v in source.items() if k not in ['evidence', 'bodyHex', 'decodedHex', 'encodedWindowHex']}, 'decodedWindowSHA256': binding.sha(decoded), 'encodedWindowSHA256': binding.sha(bytes.fromhex(source['encodedWindowHex'][2:])), 'unit': unit, 'state': state, 'questions': questions, 'tokens': tokens, 'batch': tensors, 'flatTokenIds': flat_ids, 'inputPath': str(input_path), 'inputSHA256': binding.sha(input_bytes), 'inputBytes': len(input_bytes), 'gateHashes': gate_hashes, 'cropPolicy': {'headlineMaxChars': 110, 'snippetMaxChars': 162, 'function': 'unchanged alerts_student.unit_state/cut whole words then ...', 'sequenceMaxTokens': 320, 'headMaxTokens': 160, 'combinedMaxTokens': 960, 'untruncatedStateRetainedForAllQuestions': True, 'originalSnippetCharacters': len(unit['snippet']), 'modelSnippetCharacters': len(alerts_student.cut(unit['snippet'], 162))}, 'expectedSupportConditionalOnAdmittedPair': {'A': False, 'B': True}, 'independentExpectationLimit': 'B follows complete Kagan/Soai laureate-set admission and identity exclusion, not a fabricated named-loser sentence. Model inputs contain only original extracted fields and unchanged questions.'}
        items.append(record)
    assert items[0]['unit'] == old_input['unit'], 'early Reuters baseline changed'
    old_frozen = json.loads((OLD / 'shortlist-frozen.private.json').read_text())
    old_item = next(x for x in old_frozen['items'] if x['id'] == old_input['id'])
    assert items[0]['state'] == old_item['state'] and items[0]['questions'] == old_item['questions']
    assert [{k:t[k] for k in ['question','ids','markers','qtype','stateRetained']} for t in items[0]['tokens']] == old_item['tokens']
    sources = {str(Path(m.__file__).resolve()): file_sha(m.__file__) for m in [alerts_email, alerts_student, am, common, modeling_modernbert, binding]}
    sources[str(Path(__file__).resolve())] = file_sha(__file__)
    f = {'schema': 'chemistry-5371179-input-freeze-v1', 'frozenBeforeNewInferenceAtUTC': dt.datetime.now(dt.UTC).isoformat(), 'preselectedOrder': ORDER, 'market': selection['market'], 'question': QUESTION, 'factualA': A, 'factualB': B, 'expectedIndependentBConditionalOnAdmittedExhaustivePair': True, 'sourceAdmission': selection, 'expectationAndSourceLimit': 'Credible-reporting consensus permitted. Reuters headline explicitly says pair, snippet names Kagan/Soai2026; AP independently corroborates names. AP2026Elections is navigation, not year evidence. Two Reuters versions are one reporting group. Human bundle admission is separate from per-excerpt model support.', 'profile': profile, 'profileSHA256': hashlib.sha256(json.dumps(profile, sort_keys=True, separators=(',', ':')).encode()).hexdigest(), 'modelManifestPath': str(manifest_path), 'modelManifestSHA256': MANIFEST_SHA, 'packages': packages(), 'python': sys.version, 'sourcePins': sources, 'rankingPath': str(ranking_path), 'rankingSHA256': RANKING_SHA, 'selectedWindowsPath': str(selected_path), 'selectedWindowsSHA256': file_sha(selected_path), 'items': items, 'preservedOldArtifacts': {str(OLD / n): file_sha(OLD / n) for n in ['shortlist.private.json', 'shortlist-frozen.private.json', 'shortlist-results.private.json']}, 'priorBaselineID': old_input['id'], 'priorBaselineInputExactParity': True, 'priorAbstentionPreserved': True, 'noNewForwardBeforeThisFreeze': True, 'timingLimits': ['Signed time/Received claims are not independently attested receipt.', 'Reuters earlyOct7 and APearlyOct8 precede saved endDate2026-10-08T03:59Z; laterReutersOct8 07:49Z is later than this scheduled endDate. No actual closedTime or prospective acceptance was established.', 'All selected signatures expired at wallclock; cached-key signed-time replay is separate from current-time verification.', 'Google authenticates relay bytes; publisher authorship and truth require source admission.'], 'scope': 'Local frozen full float reference and offchain extraction/tokenization; no onchain inference or semantic verdict authentication claim.'}
    save(out / 'tokens.private.json', {'questionOrder': ['q','A','B'], 'variants': [{k: i[k] for k in ['id','sourceKey','tokens','batch','flatTokenIds','inputPath','inputSHA256','gateHashes']} for i in items], 'specialTokenIds': {'cls': tok.cls_token_id, 'sep': tok.sep_token_id, 'mask': tok.mask_token_id, 'pad': tok.pad_token_id}})
    f['tokensSHA256'] = file_sha(out / 'tokens.private.json')
    save(out / 'extraction-checks.private.json', {'tests': tests, 'allPassed': True, 'counts': len(tests), 'fieldAndExistingParserParity': True, 'singlePassEntitiesWhitespaceAndQP': True, 'formatCharacterPolicy': 'U+200B preserved exactly; not whitespace stripped', 'gap': 'Offchain grammar/token parity, not onchain execution of extraction or tokenizer.'})
    f['extractionChecksSHA256'] = file_sha(out / 'extraction-checks.private.json')
    save(out / 'frozen.private.json', f)
    (out / 'frozen.sha256').write_text(file_sha(out / 'frozen.private.json') + '\n')
    print(json.dumps({'stage': 'frozen-before-forward', 'frozenSHA256': file_sha(out / 'frozen.private.json'), 'profileSHA256': f['profileSHA256'], 'variants': [{'sourceKey':i['sourceKey'],'tokenCounts':[len(t['ids']) for t in i['tokens']],'combinedTokens':len(i['flatTokenIds']),'inputBytes':i['inputBytes'],'gateHashes':{k:v for k,v in i['gateHashes'].items() if k!='tokenIdsABIHex'}} for i in items], 'extractionChecksPassed': len(tests)}), flush=True)


def validate(out):
    f = json.loads((out / 'frozen.private.json').read_text())
    assert file_sha(out / 'frozen.private.json') == (out / 'frozen.sha256').read_text().strip()
    for path, digest in f['sourcePins'].items():
        current = file_sha(path)
        if current != digest and Path(path).resolve() == Path(__file__).resolve():
            amendment = json.loads((out / 'execution-amendment.private.json').read_text())
            assert amendment['originalFrozenSHA256'] == file_sha(out / 'frozen.private.json')
            assert amendment['originalRunnerSHA256'] == digest and amendment['correctedRunnerSHA256'] == current
            assert amendment['beforeAnyForward'] is True
        else:
            assert current == digest, path
    for path, digest in f['preservedOldArtifacts'].items():
        assert file_sha(path) == digest, 'old artifact changed: ' + path
    assert file_sha(f['rankingPath']) == f['rankingSHA256']
    assert file_sha(f['selectedWindowsPath']) == f['selectedWindowsSHA256']
    assert file_sha(f['modelManifestPath']) == f['modelManifestSHA256']
    assert file_sha(out / 'tokens.private.json') == f['tokensSHA256']
    assert file_sha(out / 'extraction-checks.private.json') == f['extractionChecksSHA256']
    assert packages() == f['packages'] and sys.version == f['python']
    manifest = json.loads(Path(f['modelManifestPath']).read_text())
    runtime = pins(manifest)
    for i in f['items']:
        assert file_sha(i['rawPath']) == i['rawSHA256'] and file_sha(i['inputPath']) == i['inputSHA256']
    return f, manifest, runtime


def run(out, threads):
    import torch
    import laya.agent as am
    import laya.common as common
    import chemistry_input_binding as binding
    assert not (out / 'inference-started-v2.private.json').exists(), 'corrected run is write-once; no unreported reruns'
    f, manifest, runtime = validate(out)
    save(out / 'inference-started-v2.private.json', {'atUTC':dt.datetime.now(dt.UTC).isoformat(),'frozenSHA256':file_sha(out / 'frozen.private.json'),'executionAmendmentSHA256':file_sha(out / 'execution-amendment.private.json'),'variants':ORDER,'passesPerVariant':'one instrumented full forward + one stock parity replay','pid':os.getpid()})
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
        record = {'sourceKey':name,'candidateID':item['id'],'probabilities':probabilities,'flags':flags,'expectedConditionalOnAdmittedPair':item['expectedSupportConditionalOnAdmittedPair'],'matchesConditionalHumanSupport':flags == item['expectedSupportConditionalOnAdmittedPair'],'stockReplayExact':replay == answer,'instrumentedSeconds':seconds,'stockReplaySeconds':replay_seconds,'layers':dict(counts),'answer':answer,'rawScoringLogits':raw_output[0][0].tolist(),'tracePath':str(tensor_path),'traceSHA256':file_sha(tensor_path),'layerShapes':{k:list(v.shape) for k,v in tensors.items()},'passes':{'instrumented':1,'stockReplay':1}}
        save(out / (name + '-result.private.json'), record)
        results.append(record)
        print(json.dumps({k:v for k,v in record.items() if k in ['sourceKey','probabilities','flags','matchesConditionalHumanSupport','stockReplayExact','instrumentedSeconds','stockReplaySeconds']}),flush=True)
        assert replay == answer, 'stock float parity failed; preserved result, no tuning'
    validate(out)
    report = {'atUTC':dt.datetime.now(dt.UTC).isoformat(),'frozenSHA256':file_sha(out / 'frozen.private.json'),'executionAmendmentSHA256':file_sha(out / 'execution-amendment.private.json'),'profile':f['profile'],'loadSeconds':load_seconds,'outputs':results,'allStockParityExact':all(x['stockReplayExact'] for x in results),'noModelOrCalibrationChanges':True,'noTraining':True,'priorBaselinePreserved':True,'scope':'Stock full CPU float32,28encoder+2head. Not integer/certificate/onchain execution or settlement. All preselected versions reported, including mismatches/abstentions.'}
    save(out / 'reference-results.private.json', report)
    print(json.dumps({'stage':'complete','resultsSHA256':file_sha(out / 'reference-results.private.json'),'allStockParityExact':report['allStockParityExact']}),flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stage',choices=['freeze','run'])
    ap.add_argument('--out',type=Path,default=OUT)
    ap.add_argument('--threads',type=int,default=4)
    args = ap.parse_args()
    os.umask(0o077)
    if args.stage == 'freeze':
        freeze(args.out)
    else:
        run(args.out,args.threads)
