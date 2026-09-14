import importlib.util
import json
from pathlib import Path

import pytest


P = Path(__file__).with_name("match_metadata.py")
spec = importlib.util.spec_from_file_location("match_metadata", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_normalization_removes_stopwords_and_normalizes_case():
    assert m.normalized_words("The Café AND Proof") == ["café", "proof"]


def test_retrieval_requires_two_shared_nonstopwords_and_preserves_tie_order():
    documents = [
        {"canonical_identity": "b", "canonical_url": "https://example.test/b", "occurrence_ids": ["b1"], "title": "Alpha Beta", "description": "", "normalized_pub_date": None, "tokens": ["alpha", "beta"]},
        {"canonical_identity": "a", "canonical_url": "https://example.test/a", "occurrence_ids": ["a1", "a2"], "title": "Alpha Beta", "description": "", "normalized_pub_date": None, "tokens": ["alpha", "beta"]},
        {"canonical_identity": "one", "canonical_url": "https://example.test/one", "occurrence_ids": ["one1"], "title": "Alpha", "description": "", "normalized_pub_date": None, "tokens": ["alpha"]},
    ]
    idf, weighted = m.document_weights(documents)
    results = m.retrieve("Alpha Beta", idf, weighted)
    assert [item["canonical_identity"] for item in results] == ["a", "b"]
    assert results[0]["occurrence_ids"] == ["a1", "a2"]


def test_unmatched_question_stays_unmatched():
    idf, weighted = m.document_weights([
        {"canonical_identity": "a", "canonical_url": "https://example.test/a", "occurrence_ids": ["a1"], "title": "Alpha Beta", "description": "", "normalized_pub_date": None, "tokens": ["alpha", "beta"]}
    ])
    assert m.retrieve("Gamma Delta", idf, weighted) == []


def test_dedupe_keeps_every_occurrence_id_under_one_canonical_identity():
    records = [
        {"canonical_identity": "https://example.test/article", "record_id": "z", "canonical_url": "https://example.test/article", "metadata": {"title": "Title", "description": "Description"}, "normalized_pub_date": "2026-09-01T00:00:00Z"},
        {"canonical_identity": "https://example.test/article", "record_id": "a", "canonical_url": "https://example.test/article", "metadata": {"title": "Title", "description": "Description"}, "normalized_pub_date": "2026-09-01T00:00:00Z"},
    ]
    documents = m.dedupe_identities(records)
    assert len(documents) == 1
    assert documents[0]["occurrence_ids"] == ["a", "z"]


def test_load_markets_uses_only_id_and_question(tmp_path):
    path = tmp_path / "markets.json"
    path.write_text(json.dumps([{"marketId": "1", "question": "Will Alpha win?", "outcomeLabels": ["Yes", "No"], "rules": "unused"}]))
    markets, binding = m.load_markets(path)
    assert markets == [{"market_id": "1", "question": "Will Alpha win?"}]
    assert binding["market_count"] == 1
    path.write_text(json.dumps([{"marketId": "1", "question": "One"}, {"marketId": "1", "question": "Two"}]))
    with pytest.raises(ValueError, match="duplicate marketId"):
        m.load_markets(path)
