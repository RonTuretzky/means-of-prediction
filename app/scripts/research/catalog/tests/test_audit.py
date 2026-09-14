import json
import tempfile
import unittest
from pathlib import Path

from app.scripts.research.catalog.audit import audit_collection
from app.scripts.research.catalog.collect_partition import collect
from app.scripts.research.catalog.test_collect_partition import FakeResponse, FakeSession


class AuditTests(unittest.TestCase):
    def capture(self, output):
        collect(output, True, resume=False, sleep=lambda _: None, session=FakeSession([
            FakeResponse(200, {'markets': [{'id': 'a', 'closed': True}], 'next_cursor': 'next'}),
            FakeResponse(200, {'markets': [{'id': 'b', 'closed': True}], 'next_cursor': None}),
        ]))

    def test_valid_partition(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'capture'
            self.capture(output)
            result = audit_collection(output)
            self.assertEqual(result['rawMarketOccurrences'], 2)
            self.assertEqual(result['duplicateRequests'], 0)

    def test_cursor_gap_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'capture'
            self.capture(output)
            path = output / 'request-log.jsonl'
            entries = [json.loads(line) for line in path.read_text().splitlines()]
            entries[-1]['cursorBefore'] = 'unrelated'
            path.write_text(''.join(json.dumps(entry) + '\n' for entry in entries))
            with self.assertRaisesRegex(ValueError, 'gap'):
                audit_collection(output)

    def test_tampered_response_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'capture'
            self.capture(output)
            path = output / 'raw-pages/000001-markets.json.gz'
            data = bytearray(path.read_bytes())
            data[4] ^= 1
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                audit_collection(output)

    def test_recorded_duplicate_request_keeps_complete_cursor_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'capture'
            self.capture(output)
            log = output / 'request-log.jsonl'
            pages = [json.loads(line) for line in log.read_text().splitlines() if json.loads(line).get('kind') == 'page']
            (output / pages[1]['rawFile']).rename(output / 'raw-pages/000003-markets.json.gz')
            (output / 'raw-pages/000002-markets.json.gz').write_bytes((output / pages[0]['rawFile']).read_bytes())
            repeated = dict(pages[0], page=2, rawFile='raw-pages/000002-markets.json.gz')
            pages[1].update(page=3, rawFile='raw-pages/000003-markets.json.gz')
            log.write_text(''.join(json.dumps(row) + '\n' for row in [pages[0], repeated, pages[1]]))
            manifest_path = output / 'manifest.json'
            manifest = json.loads(manifest_path.read_bytes())
            manifest['pages'] = 3
            manifest_path.write_text(json.dumps(manifest))
            result = audit_collection(output)
            self.assertEqual(result['duplicateRequests'], 1)
            self.assertEqual(result['manifestOccurrenceCorrection'], 1)
