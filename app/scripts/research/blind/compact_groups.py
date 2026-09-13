"""Research-only, capture-preserving group-marker compaction.

The supported dialect forbids backreferences and uses only boolean matching.
Its native parser gives (...) and (?:...) identical group semantics. This pass
removes only the redundant ?: marker outside escaped literals/classes.
"""
import argparse,json,os
from pathlib import Path
from round2_matcher import compile_pattern

def compact(pattern):
    if compile_pattern(pattern)[1] is not None:return pattern
    result=[];i=0;inside=False
    while i<len(pattern):
        if pattern[i]=='\\':result.append(pattern[i:i+2]);i+=2;continue
        if pattern[i]=='[':inside=True
        elif pattern[i]==']':inside=False
        if not inside and pattern[i:i+3]=='(?:':result.append('(');i+=3;continue
        result.append(pattern[i]);i+=1
    result=''.join(result)
    if compile_pattern(result)[1] is not None:raise RuntimeError('Compaction invalidated a valid pattern')
    return result

def convert(source,target):
    data=json.loads(Path(source).read_text());patterns={p:compact(p) for p in data['patterns']}
    for w in data['witnesses']:patterns.setdefault(w['pattern'],compact(w['pattern']))
    result={'patterns':sorted(set(patterns.values())),
        'witnesses':[dict(w,pattern=patterns[w['pattern']]) for w in data['witnesses']]}
    target=Path(target)
    if target.exists():raise RuntimeError('Ablation input already exists')
    target.write_text(json.dumps(result,indent=2)+'\n')
    target.with_name(target.stem+'-lineage.json').write_text(json.dumps({'source':str(source),
        'transformation':'Only valid noncapturing group markers become capturing groups; no flags, branches, literals, boundaries or quantifiers change.',
        'patternMap':patterns,'sourcePatternBytes':sum(len(p) for p in patterns),'compactedPatternBytes':sum(len(p) for p in patterns.values()),
        'noModelCalls':True,'liveDeployment':False},indent=2)+'\n')
    print(json.dumps({'patterns':len(patterns),'changed':sum(k!=v for k,v in patterns.items()),
        'bytesBefore':sum(len(p) for p in patterns),'bytesAfter':sum(len(p) for p in patterns.values())}))

if __name__=='__main__':
    os.umask(0o077);p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('target');a=p.parse_args();convert(a.source,a.target)
