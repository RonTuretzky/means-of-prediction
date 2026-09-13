"""Pure byte-level scoring helpers; no datasets are imported by this module."""
import regex as re

def compile_pattern(pattern):
    if not isinstance(pattern,str) or not pattern:return None,'missing_pattern'
    if not pattern.isascii():return None,'non_ascii_pattern'
    if len(pattern.encode())>10000:return None,'contract_pattern_size'
    source=pattern[4:] if pattern.startswith('(?i)') else pattern
    flags=re.ASCII | (re.IGNORECASE if pattern.startswith('(?i)') else 0)
    out=[];inside=False;i=0;depth=0
    while i<len(source):
        c=source[i]
        if c=='\\':
            if i+1>=len(source):return None,'trailing_escape'
            n=source[i+1]
            if n.isalnum() and n not in 'dDwWsSnrt0':return None,'unsupported_escape_'+n
            out.append(source[i:i+2]);i+=2;continue
        if c=='[':inside=True
        elif c==']':inside=False
        if not inside:
            if c=='(':
                depth+=1
                if depth>16:return None,'contract_group_depth'
            elif c==')':depth-=1
            if c in '^$':return None,'body_anchor'
            if source[i:i+2]=='(?' and source[i:i+3]!='(?:':return None,'unsupported_group'
            if c in '*+?' and i and source[i-1] in '*+?}':return None,'unsupported_quantifier'
            if c=='.':out.append('[^\\r\\n]');i+=1;continue
            if c=='{':
                count=re.match(r'\{(\d+)(?:,(\d*))?\}',source[i:])
                if count and any(int(n)>=65535 for n in count.groups() if n):return None,'contract_repetition_size'
        out.append(c);i+=1
    try:
        compiled=re.compile(''.join(out).encode(),flags)
        if compiled.search(b'',timeout=.05):return None,'empty_match'
        return compiled,None
    except Exception:return None,'compile_error'

def search(compiled,source):
    if compiled is None:return None,False
    try:
        m=compiled.search(source.encode(),timeout=.12)
        return ({'start':m.start(),'end':m.end(),'bytes':m.end()-m.start(),'text':m.group().decode('utf-8','replace')} if m else None),False
    except TimeoutError:return None,True

def score(output,email,case):
    labels=case['publicInput']['outcomeLabels'];actual=labels.index(case['expectedOutcome'])
    patterns=[output.get('outcomeARegex'),output.get('outcomeBRegex')] if isinstance(output,dict) else [None,None]
    pairs=[compile_pattern(p) for p in patterns]
    hits=[search(p,email['html']) for p,_ in pairs]
    valid=all(e is None for _,e in pairs)
    matched=[m is not None for m,_ in hits]
    status='invalid' if not valid else 'timeout' if any(t for _,t in hits) else 'conflict' if all(matched) else 'hit' if matched[actual] else 'wrong-outcome' if matched[1-actual] else 'miss'
    return {'status':status,'validPair':valid,'errors':[e for _,e in pairs],
            'actualIndex':actual,'matches':[m for m,_ in hits],
            'patternBytes':[len(p.encode()) if isinstance(p,str) else 0 for p in patterns]}
