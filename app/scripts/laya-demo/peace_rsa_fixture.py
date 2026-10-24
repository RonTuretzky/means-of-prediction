"""Export genuine frozen Peace BBC mail proof, offline, without re-signing mail.

The saved public key supports mathematical historical replay only. No DNSSEC,
historical key ownership, independent receipt time, truth, or settlement claim.
"""
import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import quopri
import re
import subprocess
from email.utils import parsedate_to_datetime
from unittest.mock import patch

import dkim
from dkim.crypto import parse_public_key, RSASSA_PKCS1_v1_5_verify

CAST = '/Users/wk/.foundry/bin/cast'
KEY_SHA = '358d16cd1f66f6fb5f53bc3daf7adba12ab424f1cb10ab1d305e48015acf5e94'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def keccak(data):
    return subprocess.check_output([CAST, 'keccak', '0x' + data.hex()], text=True).strip()


def minimal_bytes(n):
    return n.to_bytes((n.bit_length() + 7) // 8, 'big')


def export(frozen_path, out, expected_freeze_sha):
    os.umask(0o077)
    frozen_bytes = frozen_path.read_bytes()
    assert sha(frozen_bytes) == expected_freeze_sha, 'pre-inference input freeze changed'
    frozen = json.loads(frozen_bytes)
    assert len(frozen['items']) == 1, 'initial Peace fixture admits only frozen BBC'
    assert frozen['items'][0]['rawSHA256'] == '8d6693baaf144f1366db221b970639e5f6028218f5dce91b492c17a4b49dc167'
    assert frozen['market']['fullRulesSHA256'] == 'f1ba951f9767de4eae4f2562b22bc4ad43db741fe3d30cecc5112a93eafece6d'
    windows_bytes = Path(frozen['selectedWindowsPath']).read_bytes()
    assert sha(windows_bytes) == frozen['selectedWindowsSHA256']
    windows = json.loads(windows_bytes)
    rows = []
    key_material = None
    for item in frozen['items']:
        win = windows[item['sourceKey']]
        evidence = item['sourceEvidence']
        raw = Path(item['rawPath']).read_bytes()
        assert sha(raw) == item['rawSHA256'] == evidence['rawSHA256'] == win['rawSha256'][2:]
        auth = evidence['authentication']['offlineChecks'][0]
        signed_at, expires_at = int(auth['signedAtUnix']), int(auth['expiresAtUnix'])
        snapshot = auth['keySnapshot']
        snapshot_bytes = Path(snapshot['path']).read_bytes()
        assert sha(snapshot_bytes) == snapshot['snapshotSHA256']
        entries = json.loads(snapshot_bytes)[auth['selector']]
        txts = [e['txt'] for e in entries if e['at'] == snapshot['at']]
        assert len(txts) == 1
        txt = txts[0].encode()
        assert sha(txt) == auth['keySHA256'] == KEY_SHA
        key = parse_public_key(base64.b64decode(re.search(br'(?:^|;)\s*p=([^;]+)', txt)[1], validate=True))
        modulus = minimal_bytes(key['modulus'])
        exponent = minimal_bytes(key['publicExponent'])
        assert key_material in (None, (modulus, exponent)), 'unexpected key change'
        key_material = (modulus, exponent)

        message = dkim.DKIM(raw)
        with patch('dkim.time.time', return_value=signed_at):
            sig, include_headers, sig_headers = message.verify_headerprep(0)
        assert sig[b'd'] == b'google.com' and sig[b's'] == b'20251104'
        assert sig[b'a'] == b'rsa-sha256' and sig[b'c'] == b'relaxed/relaxed'
        assert b'l' not in sig and len(sig_headers) == 1
        assert int(sig[b't']) == signed_at and int(sig[b'x']) == expires_at
        required = [b'from', b'date', b'subject', b'to', b'message-id', b'mime-version', b'content-type']
        for name in required:
            assert name in include_headers
            assert len([k for k, _ in message.headers if k.lower() == name]) == 1
        policy = dkim.CanonicalizationPolicy.from_c_value(sig[b'c'])
        body = policy.canonicalize_body(message.body)
        assert sha(body) == win['canonicalBodySha256'][2:]
        assert len(body) == win['canonicalBodyLength'] <= 196608
        assert hashlib.sha256(body).digest() == base64.b64decode(sig[b'bh'])
        offset, length = win['bodyOffset'], win['encodedLength']
        excerpt = quopri.decodestring(body[offset:offset + length])
        assert excerpt == bytes.fromhex(win['decodedHex'][2:])
        assert body == bytes.fromhex(win['bodyHex'][2:])
        assert length <= 4096
        through = dkim.HashThrough(hashlib.sha256(), debug=True)
        selected = dkim.hash_headers(through, policy, policy.canonicalize_headers(message.headers),
                                     include_headers, sig_headers[0], sig)
        header = through.hashed()
        assert sha(header) == win['canonicalHeaderSha256'][2:]
        assert header == bytes.fromhex(win['headerHex'][2:])
        assert not header.endswith(b'\r\n')
        fields = dict(selected)
        signature = base64.b64decode(re.sub(br'\s+', b'', sig[b'b']), validate=True)
        assert RSASSA_PKCS1_v1_5_verify(hashlib.sha256(header), signature, key)
        assert not RSASSA_PKCS1_v1_5_verify(hashlib.sha256(header + b'x'), signature, key)
        dns_name = b'20251104._domainkey.google.com.'

        def dnsfunc(name, **kwargs):
            assert name == dns_name, 'unexpected DNS lookup'
            return txt

        with patch('dkim.time.time', return_value=signed_at):
            assert dkim.DKIM(raw).verify(0, dnsfunc=dnsfunc)
        now_valid = False
        now_error = None
        try:
            now_valid = dkim.DKIM(raw).verify(0, dnsfunc=dnsfunc)
        except dkim.ValidationError as exc:
            now_error = str(exc)
        date = fields[b'date'].rstrip(b'\r\n').decode()
        subject = fields[b'subject'].rstrip(b'\r\n').decode()
        timestamp = int(parsedate_to_datetime(date).timestamp())
        # Date is independently signed; AP's Date precedes DKIM t= by one second.
        assert abs(timestamp - signed_at) <= 300
        proof = dict(domainName='google.com', publicKeyHash=keccak(modulus), timestamp=timestamp,
                     fromAddress='googlealerts-noreply@google.com', subject=subject,
                     bodyExcerpt=excerpt.decode(), emailNullifier=keccak(signature),
                     header='0x' + header.hex(), signature='0x' + signature.hex(),
                     canonicalBody='0x' + body.hex(), bodyOffset=offset, bodyLength=length)
        rows.append(dict(sourceKey=item['sourceKey'], rawSHA256=sha(raw), canonicalHeaderSHA256=sha(header),
                         canonicalBodySHA256=sha(body), canonicalBodyBytes=len(body), proof=proof,
                         signedAtUnix=signed_at, expiresAtUnix=expires_at,
                         fullRSAAndBodyAtSignedTime=True, currentDKIMValid=now_valid,
                         currentValidationError=now_error, expiredAsOfExport=int(dt.datetime.now(dt.UTC).timestamp()) > expires_at,
                         keySnapshot=snapshot, keySHA256=KEY_SHA,
                         headerTamperRejected=True))
    modulus, exponent = key_material
    result = dict(schema='peace-bbc-original-rsa-fixtures-v1', frozenInputSHA256=expected_freeze_sha,
                  exportedAtUTC=dt.datetime.now(dt.UTC).isoformat(),
                  exporterSHA256=sha(Path(__file__).read_bytes()),
                  exponent='0x' + exponent.hex(), modulus='0x' + modulus.hex(),
                  publicKeyHash=keccak(modulus), rows=rows,
                  signedAtUnix=[r['signedAtUnix'] for r in rows],
                  expiresAtUnix=[r['expiresAtUnix'] for r in rows],
                  validationTimeUnix=max(r['signedAtUnix'] for r in rows) + 1,
                  currentTimeUnix=int(dt.datetime.now(dt.UTC).timestamp()),
                  profileSHA256='0x' + frozen['profileSHA256'], networkUsed=False,
                  limitation='Current-clock and historical RSA/body arithmetic are reported separately against the saved key; no live DNS ownership, publisher truth, independent receipt or source-consensus claim.')
    data = (json.dumps(result, indent=2, ensure_ascii=False) + '\n').encode()
    with out.open('xb') as stream:
        stream.write(data)
    out.chmod(0o600)
    print(json.dumps(dict(path=str(out), sha256=sha(data), proofs=len(rows),
                         currentValid=sum(r['currentDKIMValid'] for r in rows),
                         historicalRSAAndBodyVerified=sum(r['fullRSAAndBodyAtSignedTime'] for r in rows))))


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--frozen', type=Path, required=True)
    cli.add_argument('--out', type=Path, required=True)
    cli.add_argument('--expected-freeze-sha', required=True)
    args = cli.parse_args()
    assert re.fullmatch(r'[0-9a-f]{64}', args.expected_freeze_sha)
    export(args.frozen, args.out, args.expected_freeze_sha)
