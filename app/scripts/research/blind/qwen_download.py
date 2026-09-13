"""Resume the exact public GGUF in bounded parallel HTTP ranges; verify before use."""
import concurrent.futures,hashlib,json,os,time,urllib.request
from pathlib import Path
ROOT=Path('/Users/wk/.local/share/means-of-prediction/qwen-model-download')
PREFIX=ROOT/'Qwen3.5-35B-A3B-Q4_K_M.gguf.part'
TOTAL=21169116992
SHA='f25d609171b8f80950a60f38696597f74025de4070682d2fb1eeffe306ca7d5d'
URL='https://huggingface.co/lmstudio-community/Qwen3.5-35B-A3B-GGUF/resolve/main/Qwen3.5-35B-A3B-Q4_K_M.gguf'
def run():
    os.umask(0o077);ROOT.mkdir(parents=True,exist_ok=True)
    manifest=ROOT/'ranges.json'
    if manifest.exists():spec=json.loads(manifest.read_text())
    else:
        prefix=PREFIX.stat().st_size
        spec={'url':URL,'sha256':SHA,'totalBytes':TOTAL,'prefixBytes':prefix,'chunkBytes':1024**3,'workers':4,
            'ranges':[[start,min(start+1024**3,TOTAL)-1] for start in range(prefix,TOTAL,1024**3)]}
        manifest.write_text(json.dumps(spec,indent=2))
    if PREFIX.stat().st_size!=spec['prefixBytes']:raise RuntimeError('Prefix changed while download prepared')
    def one(pair):
        start,end=pair;path=ROOT/(str(start)+'-'+str(end)+'.range');events=[]
        for attempt in range(6):
            have=path.stat().st_size if path.exists() else 0
            if have==end-start+1:return path
            if have>end-start+1:raise RuntimeError('Range too large')
            position=start+have;request=urllib.request.Request(URL,headers={'Range':f'bytes={position}-{end}'})
            try:
                with urllib.request.urlopen(request,timeout=90) as response:
                    expected=f'bytes {position}-{end}/{TOTAL}'
                    if response.status!=206 or response.headers.get('Content-Range')!=expected:raise RuntimeError('Unexpected HTTP range; refusing append')
                    with path.open('ab') as f:
                        while data:=response.read(1024**2):f.write(data)
                events.append({'attempt':attempt+1,'status':'complete','bytes':path.stat().st_size})
            except Exception as exc:
                events.append({'attempt':attempt+1,'status':'transport_failed','type':type(exc).__name__,'bytes':path.stat().st_size if path.exists() else 0})
                time.sleep(2)
            (ROOT/(str(start)+'.events.json')).write_text(json.dumps(events,indent=2))
            if path.exists() and path.stat().st_size==end-start+1:
                print(json.dumps({'rangeCompleted':start,'bytes':end-start+1}),flush=True);return path
        raise RuntimeError('Range transport exhausted: '+str(start))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(one,spec['ranges']))
    final=ROOT/'Qwen3.5-35B-A3B-Q4_K_M.gguf'
    if final.exists():raise RuntimeError('Completed file already exists')
    digest=hashlib.sha256()
    with final.open('wb') as out:
        for path in [PREFIX]+[ROOT/(str(start)+'-'+str(end)+'.range') for start,end in spec['ranges']]:
            with path.open('rb') as f:
                while data:=f.read(8*1024**2):out.write(data);digest.update(data)
    actual=digest.hexdigest();result={'expected':SHA,'actual':actual,'bytes':final.stat().st_size,'verified':actual==SHA and final.stat().st_size==TOTAL}
    (ROOT/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
    if not result['verified']:raise RuntimeError('Model checksum mismatch; do not load')
if __name__=='__main__':run()
