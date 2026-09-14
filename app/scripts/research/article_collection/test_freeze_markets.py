import importlib.util
from pathlib import Path

P = Path(__file__).with_name("freeze_markets.py")
spec = importlib.util.spec_from_file_location("freeze_markets", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_time_and_closed_fields_are_conservative():
    assert m.parse_time(None) is None
    assert m.parse_time("not-a-time") is None
    assert m.parse_time("2026-09-01T12:00:00") is None
    assert m.parse_time("2026-09-01T12:00:00Z") is not None
    assert m.closed_state(True) == "closed"
    assert m.closed_state(False) == "open"
    assert m.closed_state(None) == "unknown"


def test_event_identity_is_namespaced_and_multiple_events_are_excluded():
    assert m.group_key({"id": "1", "events": [{"id": "9", "slug": "same-event"}]}) == (
        "event-id:9",
        True,
    )
    assert m.group_key({"id": "2", "events": [{"slug": "9"}]}) == (
        "event-slug:9",
        True,
    )
    assert m.group_key({"id": "3", "events": []}) == ("market-id:3", False)
    assert m.group_key({"id": "4", "events": [{"id": "a"}, {"id": "b"}]}) is None
    assert m.group_key({"id": "5", "events": [{"id": "b"}, {"id": "c"}]}) is None


def test_conflict_keeps_exact_first_and_later_page_references():
    first, conflicts = {}, {}
    row_a = {"id": "1", "question": "Synthetic A"}
    row_b = {"id": "1", "question": "Synthetic B"}
    m.register_version(
        first,
        conflicts,
        market_id="1",
        row=row_a,
        page="page-a.json",
        page_hash="hash-a",
    )
    m.register_version(
        first,
        conflicts,
        market_id="1",
        row=row_b,
        page="page-b.json",
        page_hash="hash-b",
    )
    assert conflicts["1"][0] == {
        "page": "page-a.json",
        "pageSha256": "hash-a",
        "rowSha256": m.digest(m.json_bytes(row_a)),
    }
    assert conflicts["1"][1]["page"] == "page-b.json"
    assert all(item["page"] != "prior" for item in conflicts["1"])


def test_output_artifact_hash_binds_exact_bytes_and_prices_are_strict():
    raw = b"synthetic output\n"
    assert m.artifact_entry("sample.json", raw, 1) == {
        "path": "sample.json",
        "sha256": m.digest(raw),
        "bytes": len(raw),
        "count": 1,
    }
    assert not m.is_one_hot(["Yes", "No"], ["bad", 0])
    assert m.is_one_hot(["Yes", "No"], ["1", "0"])
