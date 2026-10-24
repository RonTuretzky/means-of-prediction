"""Export one frozen Google Alerts MIME byte witness, entirely offline.

No RSA verification, DNS lookup, inference, article truth or on-chain verdict is
claimed. dkimpy supplies the exact DKIM signed-header input and complete canonical
body; the signed bh= is checked locally. Private input/output paths are explicit.
The complete selected Article row and its contiguous four-field prefix are both
measured; the latter omits only subsequent sharing/layout markup. This exporter
is not the Solidity article-extraction policy or the model's input serializer.
"""
import argparse
import base64
import hashlib
import html
import importlib.metadata
import json
import os
from pathlib import Path
import quopri
import re
import sys
import urllib.parse

import dkim

RAW_SHA256 = '2d75c4968d136851825b44689fb7beddb270d36a148f3070e435236d05cc8f41'
RESULT_INDEX = 3
MAX_WINDOW = 4096


def sha(data):
    return hashlib.sha256(data).hexdigest()


def private_write(path, data):
    with path.open('xb') as stream:
        stream.write(data)
    path.chmod(0o600)


def qp_positions(encoded):
    """Map every decoded byte back to its complete original encoded token."""
    decoded = bytearray()
    positions = []
    i = 0
    while i < len(encoded):
        start = i
        if encoded[i:i + 3] == b'=\r\n':
            i += 3
            continue
        if encoded[i:i + 1] == b'=':
            assert re.fullmatch(br'[0-9A-Fa-f]{2}', encoded[i + 1:i + 3])
            decoded.append(int(encoded[i + 1:i + 3], 16))
            i += 3
        else:
            decoded.append(encoded[i])
            i += 1
        positions.append((start, i))
    assert bytes(decoded) == quopri.decodestring(encoded)
    return bytes(decoded), positions


def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', value.decode())).replace('\xa0', ' ')).strip()


def export(candidate_path, out):
    candidate_bytes = candidate_path.read_bytes()
    candidate = json.loads(candidate_bytes)
    raw = Path(candidate['raw']['path']).read_bytes()
    assert sha(raw) == candidate['raw']['sha256'] == RAW_SHA256
    assert candidate['exactUnit']['resultIndex'] == RESULT_INDEX
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'research/blind'))
    import alerts_email
    expected = candidate['exactUnit']
    parsed = alerts_email.parse(raw)['results'][RESULT_INDEX]
    for key, frozen_key in [('headline', 'headline'), ('publisher', 'publisherLabel'),
                            ('snippet', 'snippet'), ('url', 'linkedURL'), ('host', 'linkedHost')]:
        assert parsed[key] == expected[frozen_key], key

    message = dkim.DKIM(raw)
    sig, include_headers, sig_headers = message.verify_headerprep()
    assert sig[b'd'] == b'google.com' and sig[b'a'] == b'rsa-sha256'
    assert sig[b'c'] == b'relaxed/relaxed' and b'l' not in sig
    assert len(sig_headers) == 1
    original_ct = [value for key, value in message.headers if key.lower() == b'content-type']
    assert len(original_ct) == 1
    assert include_headers.count(b'content-type') == 2  # Actual sample oversigns.
    policy = dkim.CanonicalizationPolicy.from_c_value(sig[b'c'])
    canonical_body = policy.canonicalize_body(message.body)
    expected_bh = base64.b64decode(re.sub(br'\s+', b'', sig[b'bh']), validate=True)
    assert hashlib.sha256(canonical_body).digest() == expected_bh
    assert len(canonical_body) <= 196608

    # Capture dkimpy's actual hashing input, including emptied b= and its final
    # DKIM field without trailing CRLF, rather than constructing a lookalike.
    hasher = dkim.HashThrough(hashlib.sha256(), debug=True)
    selected = dkim.hash_headers(hasher, policy, policy.canonicalize_headers(message.headers),
                                 include_headers, sig_headers[0], sig)
    canonical_header = hasher.hashed()
    assert len([1 for key, _ in selected if key == b'content-type']) == 1
    assert b'\r\ndkim-signature:' in canonical_header
    assert not canonical_header.endswith(b'\r\n')

    boundary = re.search(br'boundary="([^"\r\n]+)"', original_ct[0])[1]
    delimiters = list(re.finditer(br'(?:\A|(?<=\r\n))--' + re.escape(boundary) + br'(--)?\r\n', canonical_body))
    assert len(delimiters) == 3 and delimiters[0].start() == 0
    assert not delimiters[0][1] and not delimiters[1][1] and delimiters[2][1] == b'--'
    assert delimiters[2].end() == len(canonical_body)
    part_start = delimiters[1].end()
    header_end = canonical_body.index(b'\r\n\r\n', part_start)
    payload_start = header_end + 4
    payload_end = delimiters[2].start() - 2
    part_headers = canonical_body[part_start:header_end]
    assert b'Content-Transfer-Encoding: quoted-printable' in part_headers
    encoded_html = canonical_body[payload_start:payload_end]
    decoded_html, positions = qp_positions(encoded_html)
    articles = list(re.finditer(br'<tr\b[^>]*itemtype="http://schema.org/Article"[^>]*>', decoded_html))
    article = articles[RESULT_INDEX]
    depth = 1
    full_end = None
    for tag in re.finditer(br'</?tr\b[^>]*>', decoded_html[article.end():], re.I):
        depth += -1 if tag[0].startswith(b'</') else 1
        if depth == 0:
            full_end = article.end() + tag.end()
            break
    assert full_end is not None
    row = decoded_html[article.start():full_end]
    url_match = re.search(br'<a href="([^"]+)"[^>]*itemprop="url"[^>]*>', row)
    headline = re.search(br'<span itemprop="name">(.*?)</span>', row, re.S)
    publisher = re.search(br'itemprop="publisher".*?<span itemprop="name">(.*?)</span>', row, re.S)
    description = re.search(br'<div itemprop="description"[^>]*>(.*?)</div>', row, re.S)
    assert all((url_match, headline, publisher, description))
    redirect = urllib.parse.urlparse(html.unescape(url_match[1].decode()))
    assert redirect.hostname == 'www.google.com' and redirect.path == '/url'
    assert urllib.parse.parse_qs(redirect.query)['url'] == [expected['linkedURL']]
    assert clean(headline[1]) == expected['headline']
    assert clean(publisher[1]) == expected['publisherLabel']
    assert clean(description[1]) == expected['snippet']
    assert max(url_match.end(), headline.end(), publisher.end()) < description.end()

    def window(a, z):
        start, end = positions[a][0], positions[z - 1][1]
        encoded = encoded_html[start:end]
        decoded = decoded_html[a:z]
        assert quopri.decodestring(encoded) == decoded
        assert canonical_body[payload_start + start:payload_start + end] == encoded
        return payload_start + start, encoded, decoded

    full_offset, full_encoded, full_decoded = window(article.start(), full_end)
    offset, encoded, decoded = window(article.start(), article.start() + description.end())
    all_fields = len(encoded) <= MAX_WINDOW
    if not all_fields:
        offset, encoded, decoded = window(article.start() + description.start(), article.start() + description.end())
    assert len(encoded) <= MAX_WINDOW
    fixture = {
        'schema': 1, 'parserVersion': 2, 'resultIndex': RESULT_INDEX,
        'rawSha256': '0x' + RAW_SHA256, 'candidateSha256': '0x' + sha(candidate_bytes),
        'canonicalBodySha256': '0x' + sha(canonical_body), 'canonicalBodyLength': len(canonical_body),
        'canonicalHeaderSha256': '0x' + sha(canonical_header),
        'headerHex': '0x' + canonical_header.hex(), 'bodyHex': '0x' + canonical_body.hex(),
        'bodyOffset': offset, 'encodedLength': len(encoded), 'encodedHex': '0x' + encoded.hex(),
        'decodedHex': '0x' + decoded.hex(), 'allFourFieldsIncluded': all_fields,
        'selection': 'Article opening through complete description closure; sharing/layout tail omitted' if all_fields else 'Complete description only; full four-field span exceeds MAX_WINDOW',
        'wholeRowOffset': full_offset, 'wholeRowEncodedLength': len(full_encoded),
        'wholeRowDecodedLength': len(full_decoded), 'wholeRowDecodedHex': '0x' + full_decoded.hex(),
        'wholeRowFitsWindow': len(full_encoded) <= MAX_WINDOW,
        'signedBhVerifiedLocally': True, 'actualSignedContentTypeFields': 1,
        'signedListContentTypeOccurrences': include_headers.count(b'content-type'),
        'dkimpyVersion': importlib.metadata.version('dkimpy'),
        'exporterSha256': '0x' + sha(Path(__file__).read_bytes()),
        'rsaVerifiedNow': False, 'networkUsed': False,
        'scope': 'Exact HTML byte-window authentication only; no RSA, article parser, tokenizer, inference, truth or settlement proof.',
    }
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    for name, data in [('canonical-header.bin', canonical_header), ('canonical-body.bin', canonical_body),
                       ('encoded-window.bin', encoded), ('decoded-window.bin', decoded)]:
        private_write(out / name, data)
    fixture_bytes = (json.dumps(fixture, sort_keys=True, indent=2) + '\n').encode()
    private_write(out / 'fixture.private.json', fixture_bytes)
    private_write(out / 'fixture.sha256', (sha(fixture_bytes) + '\n').encode())
    print(json.dumps({'fixturePath': str(out / 'fixture.private.json'), 'fixtureSHA256': sha(fixture_bytes),
        'canonicalBodyBytes': len(canonical_body), 'canonicalBodySHA256': sha(canonical_body),
        'bodyOffset': offset, 'encodedLength': len(encoded), 'decodedLength': len(decoded),
        'allFourFieldsIncluded': all_fields, 'wholeRowEncodedLength': len(full_encoded),
        'wholeRowDecodedLength': len(full_decoded), 'wholeRowFitsWindow': len(full_encoded) <= MAX_WINDOW,
        'rsaVerifiedNow': False}, indent=2))


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--candidate', type=Path, required=True)
    cli.add_argument('--out', type=Path, required=True)
    args = cli.parse_args()
    export(args.candidate.resolve(), args.out.resolve())
