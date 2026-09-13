"""Private supplemental evaluator. Importing this module never opens a dataset.

Future source/label reads require the separately frozen adapter and methods.
All writes use exclusive creation; interrupted inference is never resampled.
"""
import collections
import datetime
import email.parser
import email.policy
import email.utils
import hashlib
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SLIDES = ROOT.parent
QWEN = SLIDES / 'astra-qwen-nyt-round1-20260912'
REGEX = SLIDES / 'astra-nyt-round4-20260912'
RESERVATION = SLIDES.parent / 'supplemental-natural-evaluation-20260913-125243'
SEAL_SHA = '0cbba9ed889a299fa72316223422d9f209926cb1f3433f3999d59c010ac85acf'
MANIFEST_SHA = '44648a74980956336871c100cb9aab3de05c46eab6142e2cfd73738ba6c4ea23'
PUBLIC_SHA = 'efbee47e8a297b0589a5d82eace007c54ea2e888f3ab5ed104506828820ede1c'
ANNOTATIONS_SHA = '05493843ac62819edd8698c94e7955d6dcfafef172ba82012a64e9cc89613b1e'
SOURCE_MANIFEST_SHA = '02483bbd7ca3f5d23d1271cbb1f6423d2c3060f2c09c2f7625efd8c800377c86'
AUTHORITY = 'provisional_single_author_research_not_human_verified_gold'
DECISIONS = {'A', 'B', 'NEITHER', 'CONFLICT'}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    return sha(Path(path).read_bytes())


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def reject_constant(value):
    raise ValueError('Nonfinite JSON number: ' + value)


def unique_object(items):
    result = {}
    for key, value in items:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def parse_json(data):
    return json.loads(data, object_pairs_hook=unique_object, parse_constant=reject_constant)


def read(path):
    return parse_json(Path(path).read_bytes())


def once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    path.chmod(0o600)


def contained(root, relative):
    require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), 'Expected relative artifact path')
    root = Path(root).resolve()
    path = (root / relative).resolve()
    require(path.is_relative_to(root) and path != root, 'Artifact path escapes its reservation')
    return path


def verify_hashes(root, hashes):
    require(isinstance(hashes, dict) and hashes, 'Empty file seal')
    for relative, expected in hashes.items():
        require(digest(contained(root, relative)) == expected, 'Frozen file changed: ' + relative)


def method_gates(qroot=QWEN, rroot=REGEX):
    # These are prior-study artifacts, never reserved future sources or labels.
    selection = read(qroot / 'selection.json')
    verify_hashes(qroot, selection['fileHashes'])
    fresh = read(qroot / 'challenge-freeze.json')
    require(fresh['selectionSha256'] == digest(qroot / 'selection.json'), 'Fresh selection differs')
    require(fresh['methods'] == selection['freshMethods'], 'Fresh methods differ')
    require(fresh['newAstraAttempts'] == 48 and fresh['freshFixtureContentsRead'] is False, 'Missing pre-opening 48-draw freeze')
    verify_hashes(qroot, fresh['fileHashes'])
    public = read(qroot / 'independent-holdout-public.json')
    require(len(public) == len({x['marketId'] for x in public}) == 12, 'Independent public cohort differs')
    require(len(fresh['methods']) == len(set(fresh['methods'])) == 2, 'Independent method count differs')
    expected = {(x['marketId'], trial) for x in public for trial in [1, 2]}
    for method in fresh['methods']:
        records = read(qroot / f'methods/{method}/challenge-rules.json')
        require(len(records) == 24 and {(x['marketId'], x['trial']) for x in records} == expected, 'Independent Astra draw coverage differs')
    require(datetime.datetime.fromisoformat(selection['selectedAt']) <= datetime.datetime.fromisoformat(fresh['at']), 'Fresh rules predate selection')
    rx = read(rroot / 'selection.json')
    require(rx['selectedMethod'] == 'baseline', 'Supplemental regex identity differs')
    verify_hashes(rroot, rx['artifactHashes'])
    for entry in read(rroot / 'sealed-source-index.json').values():
        require(digest(contained(rroot, entry['copy'])) == entry['sha256'], 'Frozen regex source differs')
    return {
        'qwenMethods': list(dict.fromkeys(['baseline', selection['selected']])),
        'qwenSelectionSha256': digest(qroot / 'selection.json'),
        'qwenChallengeFreezeSha256': digest(qroot / 'challenge-freeze.json'),
        'regexSelectionSha256': digest(rroot / 'selection.json'),
    }


def adapter_gates(root=ROOT, qroot=QWEN, rroot=REGEX):
    frozen = read(root / 'adapter-freeze.json')
    verify_hashes(root, frozen['fileHashes'])
    methods = method_gates(qroot, rroot)
    require(methods == frozen['methods'], 'Method selection changed after adapter freeze')
    return frozen


def reservation_gates(root=RESERVATION):
    # Hashing sealed bytes is an integrity check; do not parse their content here.
    require(digest(root / 'reservation-seal.json') == SEAL_SHA, 'Reservation seal changed')
    seal = read(root / 'reservation-seal.json')
    manifest_path = contained(root, seal['manifestPath'])
    require(digest(manifest_path) == MANIFEST_SHA == seal['manifestSha256'], 'Reservation manifest changed')
    manifest = read(manifest_path)
    files = manifest['files']
    require(len(files) == manifest['fileCount'] == seal['manifestFileCount'], 'Reservation file count differs')
    require(len({x['path'] for x in files}) == len(files), 'Duplicate sealed paths')
    for entry in files:
        path = contained(root, entry['path'])
        require(path.stat().st_size == entry['bytes'] and digest(path) == entry['sha256'], 'Reserved file changed')
    for entry in seal['artifactHashes'].values():
        require(digest(contained(root, entry['path'])) == entry['sha256'], 'Reserved artifact changed')
    require((seal['emailCount'], seal['questionCount'], seal['pairCount']) == (2, 241, 482), 'Reserved cohort differs')
    require(seal['previousFixtureLabelsRead'] is False and seal['candidateMethodsRun'] is False, 'Reservation blindness declaration differs')
    return seal


def validate_schema(value, schema, definitions=None, location='$'):
    """Strict validator for the explicitly used subset of the frozen schema."""
    allowed = {'$schema', '$defs', '$ref', 'title', 'description', 'type', 'properties', 'required', 'additionalProperties', 'items', 'const', 'enum', 'minimum'}
    require(not set(schema) - allowed, 'Unsupported schema keyword at ' + location)
    definitions = schema.get('$defs', definitions or {})
    if '$ref' in schema:
        ref = schema['$ref']
        require(ref.startswith('#/$defs/') and ref.count('/') == 2, 'Unsupported schema reference')
        validate_schema(value, definitions[ref.split('/')[-1]], definitions, location)
    predicates = {
        'null': lambda x: x is None, 'boolean': lambda x: type(x) is bool,
        'integer': lambda x: type(x) is int,
        'number': lambda x: type(x) in (int, float) and math.isfinite(x),
        'string': lambda x: isinstance(x, str), 'array': lambda x: isinstance(x, list),
        'object': lambda x: isinstance(x, dict),
    }
    if 'type' in schema:
        types = schema['type'] if isinstance(schema['type'], list) else [schema['type']]
        require(all(t in predicates for t in types), 'Unsupported schema type')
        require(any(predicates[t](value) for t in types), 'Schema type mismatch at ' + location)
    if 'const' in schema:
        require(canonical(value) == canonical(schema['const']), 'Schema constant mismatch at ' + location)
    if 'enum' in schema:
        require(any(canonical(value) == canonical(v) for v in schema['enum']), 'Schema enum mismatch at ' + location)
    if 'minimum' in schema and type(value) in (int, float):
        require(value >= schema['minimum'], 'Schema minimum mismatch at ' + location)
    if isinstance(value, dict):
        properties = schema.get('properties', {})
        require(set(schema.get('required', [])) <= set(value), 'Missing fields at ' + location)
        extra = set(value) - set(properties)
        additional = schema.get('additionalProperties', True)
        require(additional is not False or not extra, 'Unexpected fields at ' + location)
        for key, item in value.items():
            if key in properties:
                validate_schema(item, properties[key], definitions, location + '.' + key)
            elif isinstance(additional, dict):
                validate_schema(item, additional, definitions, location + '.' + key)
    if isinstance(value, list) and 'items' in schema:
        for index, item in enumerate(value):
            validate_schema(item, schema['items'], definitions, f'{location}[{index}]')


def header_names(value):
    require(isinstance(value, (str, list)), 'Invalid signed-header representation')
    values = value.split(':') if isinstance(value, str) else value
    require(all(isinstance(x, str) for x in values), 'Invalid signed-header name')
    return [x.strip().lower() for x in values if x.strip()]


def dkim_tags(value):
    tags = {}
    for part in value.split(';'):
        if not part.strip():
            continue
        require('=' in part, 'Malformed DKIM tag')
        name, contents = part.split('=', 1)
        name = name.strip().lower()
        require(name and name not in tags, 'Duplicate or empty DKIM tag')
        tags[name] = contents.strip()
    return tags


def selected_signed_headers(raw_names, headers):
    # RFC6376 sections3.7/5.4.2: h order selects existing occurrences from
    # bottom to top; absent oversigned occurrences contribute no header.
    available = collections.Counter(name.lower() for name in headers.keys())
    if available['dkim-signature']:
        available['dkim-signature'] -= 1  # The current signature is separate.
    selected = []
    for name in header_names(raw_names):
        if available[name]:
            selected.append(name)
            available[name] -= 1
    return selected


def source_metadata(source, raw):
    """Expose prior validation only with unique, full-body signature linkage."""
    intake, crypto = source['intakeMetadata'], source['cryptographicVerification']
    require(intake['signatures'] == crypto['recordedSignatures'], 'Intake signature copies differ')
    headers = email.parser.BytesHeaderParser(policy=email.policy.default).parsebytes(raw)
    raw_signatures = [dkim_tags(str(value)) for value in headers.get_all('DKIM-Signature', [])]
    issues, candidates = [], []
    integrity = all(crypto.get(k) is True for k in ['rawHashMatchesIntake', 'decodedBodyReproduced', 'offlineDkimBodyHashRecomputed'])
    if not integrity:
        issues.append('Incomplete recorded identity/decoding/body-hash checks')
    for sig in intake['signatures']:
        if not (sig['result'] == 'pass' and sig['algorithm'] == 'rsa-sha256' and sig['bodyLengthLimited'] is False and sig['domain'] and sig['selector']):
            continue
        matches = [m for m in source['signedHeaderMetadata'] if (m['domain'], m['selector']) == (sig['domain'], sig['selector'])]
        same_intake = [s for s in intake['signatures'] if (s['domain'], s['selector']) == (sig['domain'], sig['selector'])]
        if len(matches) != 1 or len(same_intake) != 1:
            issues.append('Ambiguous or missing domain/selector signature linkage')
            continue
        meta = matches[0]
        if not (integrity and meta['bodyLengthLimited'] is False and meta['bodyHashMatches'] is True):
            continue
        raw_matches = [tags for tags in raw_signatures if (tags.get('d'), tags.get('s')) == (sig['domain'], sig['selector'])]
        if len(raw_matches) != 1:
            issues.append('Ambiguous or missing raw signature linkage')
            continue
        tags = raw_matches[0]
        if tags.get('a') != 'rsa-sha256' or 'l' in tags or 'h' not in tags:
            issues.append('Raw signature algorithm or full-body coverage differs')
            continue
        if header_names(tags['h']) != header_names(meta['signedHeaderNames']):
            issues.append('Raw signature h list differs from frozen extraction')
            continue
        if header_names(sig['signedHeaders']) != selected_signed_headers(meta['signedHeaderNames'], headers):
            issues.append('Recorded signed-header lists differ')
            continue
        candidates.append((sig, meta))
    domain, signed_date = '', ''
    domains = {sig['domain'] for sig, _ in candidates}
    if len(domains) == 1:
        domain = next(iter(domains))
        date_count = len(headers.get_all('Date', []))
        signed = any('date' in header_names(sig['signedHeaders']) for sig, _ in candidates)
        if signed and date_count == 1 and source.get('messageDate'):
            parsed = email.utils.parsedate_to_datetime(str(headers['Date']))
            asserted = datetime.datetime.fromisoformat(source['messageDate'].replace('Z', '+00:00'))
            require(parsed.tzinfo is not None and asserted.tzinfo is not None and parsed == asserted, 'Signed message date differs from raw header')
            signed_date = source['messageDate']
        else:
            issues.append('Signed Date unavailable or ambiguous')
    else:
        issues.append('No unique recorded validated signing domain')
    packet = {'subject': source['subject'], 'domain': domain, 'signedDate': signed_date, 'receivedAt': source.get('receivedAt') or ''}
    audit = {'priorRecordedSignaturePassesLinked': len(candidates), 'validatedDomainCount': len(domains),
             'verificationObservationTimes': [sig['checkedAt'] for sig, _ in candidates], 'issues': issues,
             'newRsaVerificationPerformedByEvaluator': False,
             'meaning': 'Retained prior intake signature observation plus frozen offline integrity checks; no new key lookup or RSA verification. Date and receipt do not establish event time.'}
    return packet, audit


def pair_id(raw_sha, market_id):
    return sha((raw_sha + '\0' + market_id).encode('utf-8'))


def layer_expected(layer, core=False):
    supported = {'supported_direct', 'supported_inferred'} if core else {'admissible'}
    status, index = layer['status'], layer['outcomeIndex']
    if status in supported:
        require(type(index) is int and index in (0, 1), 'Supported annotation lacks binary index')
        return ['A', 'B'][index]
    require(index is None, 'Unresolved annotation has indexed outcome')
    if status == 'unsupported':
        return 'NEITHER'
    require(status in {'ambiguous', 'unreviewed', 'nonbinary'}, 'Unexpected annotation status')
    require(not core or status != 'nonbinary', 'Unexpected nonbinary core fact')
    return None


def verify_annotations(rows, questions, sources, schema, reservation=RESERVATION):
    expected = {(s['rawSha256'], q['marketId']) for s in sources for q in questions}
    require(len(rows) == len(expected), 'Incomplete annotation Cartesian product')
    qindex = {q['marketId']: (i + 1, q) for i, q in enumerate(questions)}
    sindex = {s['rawSha256']: s for s in sources}
    seen = set()
    for row in rows:
        validate_schema(row, schema)
        key = row['emailSha256'], row['marketId']
        require(key in expected and key not in seen, 'Unknown or duplicate annotation pair')
        seen.add(key)
        ordinal, question = qindex[row['marketId']]
        source = sindex[row['emailSha256']]
        require(row['pairId'] == pair_id(*key) and row['emailKey'] == source['emailKey'], 'Annotation source linkage differs')
        require(row['questionOrdinal'] == ordinal and row['questionSha256'] == sha(canonical(question)), 'Annotation question linkage differs')
        require(row['ruleSha256'] == sha(question['rules'].encode('utf-8')), 'Annotation original rule differs')
        require(row['annotationAuthority'] == AUTHORITY and row['noCandidateExecution'] is True and row['noOldFixtureLabelsUsed'] is True, 'Annotation boundary declaration differs')
        layer_expected(row['coreFact'], core=True)
        layer_expected(row['originalRuleSettlement'])
        nonbinary = row['originalRuleSettlement']['nonbinaryOutcome']
        require((isinstance(nonbinary, str) and bool(nonbinary)) if row['originalRuleSettlement']['status'] == 'nonbinary' else nonbinary is None, 'Nonbinary annotation mapping differs')
        partial = any(row[k]['status'] == 'unreviewed' for k in ['coreFact', 'originalRuleSettlement'])
        require(row['reviewStatus'] == ('partial' if partial else 'reviewed'), 'Annotation review coverage differs')
        for evidence in row['coreFact']['evidence']:
            require(evidence['sourcePath'] == source['decodedTextPath'], 'Evidence is outside the authorized decoded text')
            text = contained(reservation, evidence['sourcePath']).read_bytes().decode('utf-8')
            start, end = evidence['startCharacter'], evidence['endCharacter']
            require(0 <= start <= end <= len(text) and text[start:end] == evidence['text'], 'Evidence Unicode span differs')
            require(sha(evidence['text'].encode('utf-8')) == evidence['textSha256'], 'Evidence text hash differs')
    require(seen == expected, 'Missing annotation pair')


def decision(mask):
    require(len(mask) == 2 and all(type(x) is bool for x in mask), 'Invalid predicate mask')
    return 'CONFLICT' if all(mask) else 'A' if mask[0] else 'B' if mask[1] else 'NEITHER'


def execution_summary(rows, model_requests):
    if not model_requests:
        return {'predictionRows': len(rows), 'modelRequests': 0, 'matcherDurationMeasured': False,
                'qualification': 'Deterministic regex evaluation makes no model requests. Matcher duration was not measured.'}
    skipped = {'rule_or_html_unavailable', 'full_input_overflow'}
    attempted = [row for row in rows if row['status'] not in skipped]
    seconds = [row['seconds'] for row in attempted if type(row.get('seconds')) in (int, float)
               and math.isfinite(row['seconds']) and row['seconds'] >= 0]
    counts = {key: [row['usage'][key] for row in attempted if isinstance(row.get('usage'), dict)
                   and type(row['usage'].get(key)) is int and row['usage'][key] >= 0]
              for key in ['prompt_tokens', 'completion_tokens']}
    return {'predictionRows': len(rows), 'modelRequests': len(attempted),
            'skippedByStatus': dict(collections.Counter(row['status'] for row in rows if row['status'] in skipped)),
            'recordedRequestSeconds': sum(seconds), 'medianRequestSeconds': statistics.median(seconds) if seconds else None,
            'requestsWithRecordedSeconds': len(seconds), 'attemptedWithoutRecordedSeconds': len(attempted) - len(seconds),
            'knownPromptTokens': sum(counts['prompt_tokens']), 'knownCompletionTokens': sum(counts['completion_tokens']),
            'requestsWithPromptUsage': len(counts['prompt_tokens']), 'attemptedWithoutPromptUsage': len(attempted) - len(counts['prompt_tokens']),
            'requestsWithCompletionUsage': len(counts['completion_tokens']), 'attemptedWithoutCompletionUsage': len(attempted) - len(counts['completion_tokens']),
            'qualification': 'Known totals are lower bounds when usage or duration is missing. Concurrent summed request seconds are not wall time.'}


def score_layer(predictions, annotations, layer, prediction_field):
    groups = collections.defaultdict(list)
    for pair, row in annotations.items():
        prediction = predictions[pair]
        label = row[layer]
        expected = layer_expected(label, core=layer == 'coreFact')
        value = prediction.get(prediction_field) if prediction['valid'] else 'UNSCORABLE'
        require(value in DECISIONS | {'UNSCORABLE'}, 'Unexpected candidate decision')
        groups[label['status']].append((expected, value, prediction.get('exactQuote', False)))
    result = {}
    for status, rows in sorted(groups.items()):
        eligible = [x for x in rows if x[0] is not None]
        completed = [x for x in rows if x[1] != 'UNSCORABLE']
        correct = sum(expected is not None and expected == value for expected, value, _ in rows)
        result[status] = {'pairs': len(rows), 'eligiblePairs': len(eligible), 'completed': len(completed),
            'unscorable': len(rows) - len(completed), 'decisions': dict(collections.Counter(v for _, v, _ in rows)),
            'correctFullEligibleNumerator': correct, 'fullEligibleDenominator': len(eligible),
            'completedEligibleDenominator': sum(e is not None and v != 'UNSCORABLE' for e, v, _ in rows),
            'exactQuoteCorrectSupported': sum(e in ('A', 'B') and e == v and quoted for e, v, quoted in rows),
            'exclusiveClaims': sum(v in ('A', 'B') for _, v, _ in rows),
            'anyPredicateClaimIncludingConflict': sum(v in ('A', 'B', 'CONFLICT') for _, v, _ in rows),
            'namedNonbinaryResolutionMeasured': False}
    return result
