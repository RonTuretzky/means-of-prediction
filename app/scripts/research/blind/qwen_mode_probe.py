"""Separate native-API reasoning-mode capability diagnostic; never benchmark data."""
import argparse
import concurrent.futures
import http.client
import json
import os
import time
from pathlib import Path
import qwen_round1 as q


def request_for(item, rule, mode):
    baseline = q.judge_request(rule, q.restore_email(item['email']), (q.ROOT / 'baseline-judge.txt').read_text(), q.load('runtime.json'))
    return {'model': baseline['model'], 'input': baseline['messages'][1]['content'],
            'system_prompt': baseline['messages'][0]['content'], 'reasoning': mode,
            'temperature': 0, 'top_p': 0.95, 'top_k': 40, 'min_p': 0.05,
            'repeat_penalty': 1.1, 'max_output_tokens': 2048, 'store': False,
            'stream': False, 'integrations': []}


def call(request, directory):
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / 'request.json').exists() and q.r.read(directory / 'request.json') != request:
        raise RuntimeError('Probe request changed')
    if (directory / 'result.json').exists(): return q.r.read(directory / 'result.json')
    if (directory / 'started.json').exists(): raise RuntimeError('Uncertain probe; do not restart')
    q.r.save(directory / 'request.json', request)
    q.r.save(directory / 'started.json', {'at': q.r.now(), 'pid': os.getpid()})
    start = time.time(); connection = http.client.HTTPConnection('127.0.0.1', 1234, timeout=2700)
    try:
        connection.request('POST', '/api/v1/chat', json.dumps(request, ensure_ascii=False).encode(), {'Content-Type': 'application/json'})
        response = connection.getresponse(); raw = response.read()
        (directory / 'response.raw').write_bytes(raw)
        data = json.loads(raw); q.r.save(directory / 'response.json', data)
        messages = [x['content'] for x in data.get('output', []) if x.get('type') == 'message']
        try: output = json.loads(''.join(messages)); valid = q.valid_judgment(output)
        except (ValueError, TypeError): output = None; valid = False
        stats = data.get('stats', {})
        result = {'status': 'completed' if response.status == 200 and valid else 'failed', 'output': output,
                  'httpStatus': response.status, 'seconds': time.time()-start,
                  'requestSha256': q.r.hash_value(request), 'rawResponseSha256': q.r.digest(directory / 'response.raw'),
                  'responseSha256': q.r.digest(directory / 'response.json'), 'nativeStats': stats,
                  'reasoningCharacters': sum(len(x.get('content', '')) for x in data.get('output', []) if x.get('type') == 'reasoning'),
                  'returnedModel': data.get('model_instance_id'), 'messageCount': len(messages),
                  'usage': {'prompt_tokens': stats['input_tokens'], 'completion_tokens': stats['total_output_tokens']} if stats else None,
                  'maxTokensPossiblyReached': stats.get('total_output_tokens') == request['max_output_tokens']}
    except Exception as exc:
        result = {'status': 'transport_failed', 'output': None, 'exceptionType': type(exc).__name__,
                  'seconds': time.time()-start, 'requestSha256': q.r.hash_value(request)}
    finally: connection.close()
    q.r.save(directory / 'result.json', result)
    return result


def main(limit, workers):
    os.umask(0o077)
    panel = q.load('runtime-mode-diagnostic-panel.json')['cases'][:limit]
    items = {x['caseId']: x for x in q.load(q.ITEMS)}
    rules = {x['marketId']: x for x in q.load('methods/baseline/rules.json')}
    tasks = [(entry, mode) for entry in panel for mode in ['off', 'on']]
    def one(task):
        entry, mode = task; item = items[entry['caseId']]
        result = call(request_for(item, rules[item['marketId']]['output'], mode), q.ROOT / 'runtime-probes/native-mode' / item['caseId'] / mode)
        row = {**entry, 'mode': mode, **result, 'score': q.score_record(item, {'trial': 1, **result})}
        print(json.dumps({k: row[k] for k in ['caseId', 'mode', 'status', 'httpStatus', 'seconds', 'reasoningCharacters'] if k in row}), flush=True)
        return row
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool: rows = list(pool.map(one, tasks))
    q.once(f'runtime-mode-diagnostic-results-{limit}.private.json', {'at': q.r.now(), 'rows': rows,
           'qualification': 'Targeted development capability probe. Same frozen rule, whole semantic email and system prompt; native reasoning off/on, no JSON grammar or documented seed option. Endpoint, grammar and seed support differ from the scored baseline. No causal attribution or benchmark promotion from this panel. Native mode is per request; no loaded-instance default changed.'})


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--limit', type=int, default=1); p.add_argument('--workers', type=int, default=2); a = p.parse_args(); main(a.limit, a.workers)
