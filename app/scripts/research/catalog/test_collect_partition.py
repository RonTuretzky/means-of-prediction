import importlib.util
import json
import pathlib
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "collector", pathlib.Path(__file__).with_name("collect_partition.py")
)
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class FakeResponse:
    def __init__(self, status, payload, headers=None):
        self.status_code = status
        self.payload = payload
        self.content = json.dumps(payload).encode()
        self.headers = headers or {}

    def json(self):
        return self.payload

    def __bool__(self):
        return self.status_code < 400


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class CollectorTests(unittest.TestCase):
    def test_mock_multipage_exhaustion_finishes_with_null_cursor(self):
        session = FakeSession(
            [
                FakeResponse(200, {"markets": [{"id": "1"}], "next_cursor": "opaque"}),
                FakeResponse(200, {"markets": [{"id": "2"}], "next_cursor": None}),
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / "closed"
            self.assertEqual(
                collector.collect(output, True, resume=False, session=session, sleep=lambda _: None),
                0,
            )
            manifest = json.loads((output / "manifest.json").read_bytes())
            checkpoint = json.loads((output / "checkpoint.json").read_bytes())
            self.assertTrue(manifest["complete"])
            self.assertEqual(manifest["pages"], 2)
            self.assertEqual(manifest["marketOccurrences"], 2)
            self.assertIsNone(checkpoint["nextCursor"])

    def test_http_403_is_recorded_and_stops_without_fallback(self):
        session = FakeSession([FakeResponse(403, {"error": "synthetic forbidden"})])
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / "closed"
            self.assertEqual(
                collector.collect(output, True, resume=False, session=session, sleep=lambda _: None),
                1,
            )
            self.assertEqual(len(session.calls), 1)
            entries = [json.loads(line) for line in (output / "request-log.jsonl").read_text().splitlines()]
            self.assertEqual(entries[0]["httpStatus"], 403)
            self.assertTrue(entries[0]["errorBodyFile"].endswith(".http.gz"))
            self.assertFalse((output / "manifest.json").exists())
            self.assertEqual(len(list((output / "failure-receipts").glob("run-*.json"))), 1)

    def test_429_honors_long_retry_after_then_succeeds(self):
        session = FakeSession(
            [
                FakeResponse(429, {"error": "synthetic rate limit"}, {"Retry-After": "125"}),
                FakeResponse(200, {"markets": [], "next_cursor": None}),
            ]
        )
        sleeps = []
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / "closed"
            result = collector.collect(
                output, True, resume=False, session=session, sleep=sleeps.append
            )
            self.assertEqual(result, 0)
            self.assertEqual(sleeps, [125.0])
            self.assertEqual(len(session.calls), 2)

    def test_resume_rejects_partition_mismatch(self):
        session = FakeSession([FakeResponse(403, {"error": "synthetic"})])
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / "closed"
            collector.collect(output, True, resume=False, session=session, sleep=lambda _: None)
            with self.assertRaisesRegex(RuntimeError, "--closed"):
                collector.collect(
                    output,
                    False,
                    resume=True,
                    session=FakeSession([]),
                    sleep=lambda _: None,
                )


if __name__ == "__main__":
    unittest.main()
