"""Shared artifact pinning and integer reference utilities; no model execution."""
import hashlib,json,math,struct
from pathlib import Path

def sha(b): return hashlib.sha256(b).hexdigest()
def file_sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''): h.update(b)
    return h.hexdigest()
def save(p,obj):
    with open(p,'x') as f: json.dump(obj,f,ensure_ascii=False,indent=2); f.write('\n')
    p.chmod(0o600)
def hash_tree(leaves):
    nodes=[hashlib.sha256(b'\x00'+struct.pack('>Q',i)+bytes.fromhex(h)).digest() for i,h in enumerate(leaves)]
    while len(nodes)>1:
        if len(nodes)%2:nodes.append(nodes[-1])
        nodes=[hashlib.sha256(b'\x01'+nodes[i]+nodes[i+1]).digest() for i in range(0,len(nodes),2)]
    return nodes[0].hex()
def pin_checkpoint(model_dir):
    weights=model_dir/'model.safetensors'; chunks=[]; h=hashlib.sha256()
    with weights.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):
            h.update(b);chunks.append({'index':len(chunks),'bytes':len(b),'sha256':sha(b)})
        f.seek(0); header=json.loads(f.read(struct.unpack('<Q',f.read(8))[0]))
    entries={k:v for k,v in header.items() if k!='__metadata__'}
    n=sum(math.prod(v['shape']) for v in entries.values())
    # Pin only files loaded from this checkpoint, not nested sibling checkpoints/logs.
    paths=[model_dir/'rl_agent_config.json']
    for folder in ('encoder','tokenizer'):
        paths.extend(p for p in (model_dir/folder).rglob('*') if p.is_file())
    small={str(p.relative_to(model_dir)):file_sha(p) for p in sorted(paths)}
    leaves=[c['sha256'] for c in chunks]
    assert hash_tree(leaves)!=hash_tree(leaves[::-1]), 'Order must bind root'
    assert hash_tree(leaves)!=hash_tree(leaves[:-1]), 'Missing chunk must alter root'
    corrupted=leaves.copy();corrupted[0]='00'*32
    assert hash_tree(leaves)!=hash_tree(corrupted), 'Mutated chunk must alter root'
    return {'path':str(model_dir),'weightBytes':weights.stat().st_size,'weightsSha256':h.hexdigest(),'chunkSize':4*1024*1024,'chunks':chunks,'chunkRootSha256':hash_tree(leaves),'chunkTreeFormat':'SHA256 leaf(0x00||u64be(index)||chunkSHA256); branch(0x01||left||right); duplicate odd last','smallFilesSha256':small,'parameterCount':n,'tensors':entries,'chunkMutationChecks':True}
def q6_layernorm(x,gamma):
    n=len(x);s=sum(x);variance=sum((n*v-s)**2 for v in x)//(n*n*n)
    den=n*math.isqrt((variance+10_000_000)*10**12)
    nums=[(n*v-s)*g*10**6 for v,g in zip(x,gamma)]
    return [(abs(v)//den)*(1 if v>=0 else -1) for v in nums]
