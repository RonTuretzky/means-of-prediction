"""Load only the verified research GGUF; never unload another user's model."""
import datetime,json,pathlib,plistlib,subprocess,time,urllib.request,os
ROOT=pathlib.Path('/Users/wk/.local/share/means-of-prediction/slides/astra-qwen-nyt-round1-20260912')
DOWNLOAD=pathlib.Path('/Users/wk/.local/share/means-of-prediction/qwen-model-download')
IDENTIFIER='mop-qwen35b-research'
def save(name,value):
    path=ROOT/name
    if path.exists():raise RuntimeError('Bootstrap artifact exists: '+name)
    path.write_text(json.dumps(value,indent=2))
def command(name,args):
    result=subprocess.run(args,capture_output=True,text=True)
    save(name,{'args':args,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    if result.returncode:raise RuntimeError('Bootstrap command failed; inspect '+name)
    return result.stdout
def main():
    os.umask(0o077)
    while not (DOWNLOAD/'verification.json').exists():time.sleep(15)
    verified=json.loads((DOWNLOAD/'verification.json').read_text())
    if not verified['verified'] or verified['actual']!='f25d609171b8f80950a60f38696597f74025de4070682d2fb1eeffe306ca7d5d':raise RuntimeError('Unverified GGUF')
    before=json.loads(command('runtime-before-load.json',['lms','ps','--json']))
    source=DOWNLOAD/'Qwen3.5-35B-A3B-Q4_K_M.gguf'
    command('runtime-import.json',['lms','import',str(source),'--user-repo','mop-research/Qwen3.5-35B-A3B-GGUF','--hard-link','-y'])
    model='mop-research/Qwen3.5-35B-A3B-GGUF/Qwen3.5-35B-A3B-Q4_K_M.gguf'
    query=source.name
    catalog=json.loads(command('runtime-catalog.json',['lms','ls','--json']))
    if [x['path'] for x in catalog if query in x.get('path','')]!=[model]:raise RuntimeError('Filename must uniquely identify the verified model')
    # This CLI build rejects correct full paths under --exact. Require a unique
    # filename match, then independently verify the loaded artifact path.
    command('runtime-estimate.json',['lms','load',query,'--gpu','max','--context-length','131072','--parallel','4','--estimate-only','-y'])
    command('runtime-load.json',['lms','load',query,'--gpu','max','--context-length','131072','--parallel','4','--identifier',IDENTIFIER,'-y'])
    current=json.loads(command('runtime-after-load.json',['lms','ps','--json']))
    if [x['path'] for x in current if x.get('identifier')==IDENTIFIER]!=[model]:raise RuntimeError('Loaded artifact differs from verified model')
    engines=command('runtime-engines.json',['lms','runtime','ls'])
    api=json.load(urllib.request.urlopen('http://127.0.0.1:1234/api/v1/models',timeout=30))
    version=plistlib.load(open('/Applications/LM Studio.app/Contents/Info.plist','rb'))
    save('runtime-draft.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'identifier':IDENTIFIER,'modelKey':model,
        'artifactPath':str(source),'artifactSha256':verified['actual'],'artifactBytes':verified['bytes'],'quantization':'Q4_K_M',
        'model':'Qwen3.5-35B-A3B','format':'GGUF','contextLength':131072,'parallelPredictions':4,'gpu':'max',
        'lmStudioVersion':version.get('CFBundleShortVersionString'),'lmStudioBuild':version.get('CFBundleVersion'),
        'priorLoadedModels':before,'loadedModels':current,'modelApi':api,'engines':engines,
        'thinkingControl':'Pending smoke verification; chat_template_kwargs enable_thinking:false is requested, not assumed honored.',
        'localOnly':True,'onchainBitExact':False})
    print(json.dumps({'loaded':IDENTIFIER,'draftRuntime':str(ROOT/'runtime-draft.json')}),flush=True)
if __name__=='__main__':main()
