"""A single isolated Astra response, using the installed Codex sign-in transport.

The loopback adapter forwards authentication only to the original OpenAI service.
It constructs a new tool-free model request from an explicit, audited public-input
job. Codex's workspace/history/tool context never reaches the generation model.
Neither headers nor credentials are written to disk. Raw completion output and
token accounting are retained; the experiment coordinator controls all file I/O.
"""
import argparse, hashlib, http.client, http.server, json, os, secrets
import subprocess, tempfile, threading, time
from pathlib import Path

UPSTREAM = 'chatgpt.com'
MODEL = 'gpt-6-astra'

def build_request(job):
    body = {
        'model': MODEL, 'instructions': job['instructions'],
        'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': json.dumps(job['input'], ensure_ascii=False)}]}],
        'reasoning': {'effort': job.get('effort', 'high')},
        'tools': [], 'tool_choice': 'none', 'parallel_tool_calls': False,
        'store': False, 'stream': True,
        'text': {'format': {'type': 'json_schema', 'name': 'blind_generation', 'strict': True, 'schema': job['schema']}},
    }
    if job.get('maxOutputTokens') is not None:
        body['max_output_tokens'] = job['maxOutputTokens']
    return body

def run(job, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    capability = secrets.token_hex(24)
    state = {'requests': [], 'events': [], 'outputItems': []}
    body = build_request(job)
    payload = json.dumps(body, ensure_ascii=False).encode()
    # This is the exact request sent to the model; it contains no auth headers.
    (output_dir/'model-request.json').write_bytes(payload)
    def checkpoint():
        temporary=output_dir/'transport-checkpoint.json.tmp'
        temporary.write_text(json.dumps(state,indent=2))
        temporary.replace(output_dir/'transport-checkpoint.json')

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'
        def log_message(self, *args): pass
        def do_GET(self): self.send_error(404)
        def do_POST(self):
            if not self.path.startswith('/'+capability+'/'):
                self.send_error(403); return
            size = int(self.headers.get('Content-Length', '0'))
            if size > 4*1024*1024:
                self.send_error(413); return
            # Discard all client-supplied model context. Only the audited job is sent.
            self.rfile.read(size)
            state['incomingHeaderNames'] = sorted(k.lower() for k in self.headers)
            state['incomingContentType'] = self.headers.get('Content-Type')
            headers = {k.lower(): v for k, v in self.headers.items() if k.lower() in
                       {'authorization','chatgpt-account-id','originator','user-agent','openai-beta'}}
            headers['Content-Type'] = 'application/json'
            headers['Accept'] = 'text/event-stream'
            connection = http.client.HTTPSConnection(UPSTREAM, timeout=600)
            try:
                connection.request('POST', '/backend-api/codex/responses', body=payload, headers=headers)
                response = connection.getresponse()
                state['requests'].append({'pathSuffix': self.path.rsplit('/',1)[-1], 'status': response.status,
                                          'requestSha256': hashlib.sha256(payload).hexdigest()})
                checkpoint()
                self.send_response(response.status)
                self.send_header('Content-Type', response.getheader('Content-Type','text/event-stream'))
                self.end_headers()
                for line in response:
                    if line.startswith(b'data: '):
                        try:
                            event = json.loads(line[6:])
                            if event.get('type') in ['response.completed','response.incomplete','response.failed']:
                                state['events'].append(event)
                                checkpoint()
                            elif event.get('type') == 'response.output_item.done':
                                if event['item'].get('type')=='message':
                                    state['outputItems'].append(event['item'])
                                    checkpoint()
                            elif event.get('type') in ['error','response.error']:
                                state.setdefault('streamErrors',[]).append(event)
                                checkpoint()
                        except (ValueError,UnicodeDecodeError): pass
                    if response.status >= 400:
                        state.setdefault('serviceErrors', []).append(line.decode('utf-8','replace')[:2000])
                    self.wfile.write(line); self.wfile.flush()
                state['upstreamStreamClosed']=True
                checkpoint()
            except Exception as exc:
                state.setdefault('transportErrors',[]).append(type(exc).__name__)
                checkpoint()
            finally: connection.close()

    server = http.server.ThreadingHTTPServer(('127.0.0.1',0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    started = time.time()
    with tempfile.TemporaryDirectory(prefix='mop-blind-client-') as cwd:
        # No repository context, local tools, saved conversation or user config.
        command = ['codex','exec','--ignore-user-config','--ignore-rules','--ephemeral',
            '--skip-git-repo-check','--sandbox','read-only','--model',MODEL,'--json','--cd',cwd,
            '-c','project_doc_max_bytes=0','-c','model_provider="blind_astra"',
            '-c','model_providers.blind_astra.name="Audited blind Astra generation"',
            '-c',f'model_providers.blind_astra.base_url="http://127.0.0.1:{server.server_port}/{capability}"',
            '-c','model_providers.blind_astra.requires_openai_auth=true',
            '-c','model_providers.blind_astra.wire_api="responses"',
            '-c','model_providers.blind_astra.supports_websockets=false',
            '-c','model_providers.blind_astra.request_max_retries=0',
            '-c','model_providers.blind_astra.stream_max_retries=0',
            '-c','features.shell_tool=false','-c','features.multi_agent=false',
            '-c','web_search="disabled"','-o',str(output_dir/'output.txt'),'-']
        with (output_dir/'client-events.jsonl').open('w') as stdout, (output_dir/'client-stderr.log').open('w') as stderr:
            process = subprocess.Popen(command,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,text=True)
            (output_dir/'process.json').write_text(json.dumps({'pid':process.pid,'startedAt':started,'model':MODEL}))
            # The adapter binds this job out-of-band. No research/evaluation data here.
            # A long response is not an excuse to silently discard or restart it.
            # The service stream has its own terminal network timeout.
            process.communicate('Produce the requested JSON response. Do not call tools.')
            state['clientExitCode'] = process.returncode
    server.shutdown(); server.server_close()
    state['seconds'] = time.time()-started
    state['requestedMaxOutputTokens'] = job.get('maxOutputTokens')
    state['model'] = MODEL
    (output_dir/'transport-result.json').write_text(json.dumps(state,indent=2))
    return state

if __name__ == '__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('job');parser.add_argument('output');args=parser.parse_args()
    result=run(json.loads(Path(args.job).read_text()),args.output)
    print(json.dumps({'model':result['model'],'httpStatuses':[r['status'] for r in result['requests']],
                      'clientExitCode':result['clientExitCode'],'seconds':round(result['seconds'],2)}))
