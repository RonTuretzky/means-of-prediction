r"""Round-two dialect adapter; preserves immutable round-one scoring semantics.

The old validator rejects an optional escaped literal, such as ``\+?``, as a
lazy quantifier because it inspects characters rather than tokens. Track the
previous quantifier token instead. Original benchmark files remain unchanged.
"""
import matcher as prior
import regex as re

def compile_pattern(pattern):
    if not isinstance(pattern,str) or not pattern:return None,'missing_pattern'
    if not pattern.isascii():return None,'non_ascii_pattern'
    if len(pattern.encode())>10000:return None,'contract_pattern_size'
    source=pattern[4:] if pattern.startswith('(?i)') else pattern
    flags=re.ASCII|(re.IGNORECASE if pattern.startswith('(?i)') else 0)
    out=[];inside=False;i=0;depth=0;last_repeat=False
    while i<len(source):
        c=source[i]
        if c=='\\':
            if i+1>=len(source):return None,'trailing_escape'
            n=source[i+1]
            if n.isalnum() and n not in 'dDwWsSnrt0':return None,'unsupported_escape_'+n
            out.append(source[i:i+2]);i+=2;last_repeat=False;continue
        if c=='[':inside=True
        elif c==']':inside=False
        if not inside:
            if c=='(':
                depth+=1
                if depth>16:return None,'contract_group_depth'
            elif c==')':depth-=1
            if c in '^$':return None,'body_anchor'
            if source[i:i+2]=='(?' and source[i:i+3]!='(?:':return None,'unsupported_group'
            if c in '*+?' and last_repeat:return None,'unsupported_quantifier'
            if c=='.':out.append('[^\\r\\n]');i+=1;last_repeat=False;continue
            if c=='{':
                count=re.match(r'\{(\d+)(?:,(\d*))?\}',source[i:])
                if count:
                    if last_repeat:return None,'unsupported_quantifier'
                    if any(int(n)>=65535 for n in count.groups() if n):return None,'contract_repetition_size'
                    out.append(count[0]);i+=len(count[0]);last_repeat=True;continue
        last_repeat=not inside and c in '*+?'
        out.append(c);i+=1
    try:
        compiled=re.compile(''.join(out).encode(),flags)
        if compiled.search(b'',timeout=.05):return None,'empty_match'
        return compiled,None
    except Exception:return None,'compile_error'

search=prior.search

def score(output,email,case):
    actual=case['publicInput']['outcomeLabels'].index(case['expectedOutcome'])
    patterns=[output.get(k) for k in ['outcomeARegex','outcomeBRegex']] if isinstance(output,dict) else [None,None]
    pairs=[compile_pattern(p) for p in patterns];hits=[search(p,email['html']) for p,error in pairs]
    valid=all(error is None for _,error in pairs);matched=[m is not None for m,t in hits]
    status='invalid' if not valid else 'timeout' if any(t for m,t in hits) else 'conflict' if all(matched) else 'hit' if matched[actual] else 'wrong-outcome' if matched[1-actual] else 'miss'
    return {'status':status,'validPair':valid,'errors':[error for _,error in pairs],'actualIndex':actual,
        'matches':[m for m,t in hits],'patternBytes':[len(p.encode()) if isinstance(p,str) else 0 for p in patterns]}

def score_controls(output,controls):
    pairs=[compile_pattern(output.get(k)) for k in ['outcomeARegex','outcomeBRegex']] if isinstance(output,dict) else [(None,'missing')]*2
    rows=[]
    for c in controls:
        hits=[search(p,c['html']) for p,e in pairs];mask=[m is not None for m,t in hits]
        expected={'A':[True,False],'B':[False,True],'neither':[False,False]}[c['expected']]
        valid=all(e is None for p,e in pairs) and not any(t for m,t in hits)
        rows.append({'name':c['name'],'kind':c['kind'],'expected':c['expected'],'matched':mask,'scorable':valid,
            'falsePositive':c['expected']=='neither' and any(mask),'passed':valid and mask==expected})
    return rows
