"""Map source-byte matches back to the authenticated encoded body, without cuts."""
import base64

def witness(email,match,compiled):
    if not match or compiled is None:return {'compatible':False,'reason':'No valid source match'}
    if not email.get('profileCompatible'):return {'compatible':False,'reason':email.get('profileError') or 'Unsupported email profile'}
    body=base64.b64decode(email['canonicalBodyBase64'])
    if len(body)>196608:return {'compatible':False,'reason':'Full encoded body exceeds 192 KiB'}
    offsets=[];decoded=bytearray();i=0
    while i<len(body):
        if email['encoding']==1 and body[i]==61:
            if body[i+1:i+3]==b'\r\n':i+=3;continue
            try:value=int(body[i+1:i+3],16)
            except ValueError:return {'compatible':False,'reason':'Malformed quoted-printable mapping'}
            if len(body[i+1:i+3])!=2:return {'compatible':False,'reason':'Incomplete quoted-printable escape'}
            offsets.append(i);decoded.append(value);i+=3
        else:offsets.append(i);decoded.append(body[i]);i+=1
    offsets.append(len(body))
    if bytes(decoded)!=email['html'].encode():return {'compatible':False,'reason':'Canonical-body mapping differs from scored HTML source'}
    for extra in range(12):
        a=max(0,match['start']-extra);b=min(len(decoded),match['end']+extra)
        if b>=len(offsets):continue
        start=offsets[a];length=offsets[b]-start
        if length<=0 or length>4096:continue
        try:
            text=decoded[a:b].decode()
            if compiled.search(text.encode(),timeout=.12):return {'compatible':True,'encodedOffset':start,'encodedBytes':length,
                'encodedBase64':base64.b64encode(body[start:start+length]).decode(),'decodedSource':text}
        except (UnicodeDecodeError,TimeoutError):continue
    return {'compatible':False,'reason':'First matched passage has no <=4 KiB byte-aligned witness'}
