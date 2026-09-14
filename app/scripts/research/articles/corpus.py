"""Deterministic, local-only article corpus imports.

This module does no retrieval. It accepts already-downloaded NYT API metadata or
explicitly declared full-text exports and stores the original bytes alongside
normalized records.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit


SCHEMA_VERSION = "article-corpus-v1"
FULL_TEXT_SCHEMA_VERSION = "article-full-text-v1"
NYT_SOURCE_KINDS = {
    "archive": "nyt_archive_api_metadata",
    "article-search": "nyt_article_search_api_metadata",
}
FULL_TEXT_SOURCE_KINDS = {
    "user_full_text_export",
    "publisher_full_text_export",
}
COMPLETENESS_VALUES = {"complete", "partial"}
PROVENANCE_FIELDS = {
    "declared_by",
    "acquisition_method",
    "source_reference",
}


class ValidationError(ValueError):
    """The supplied input does not meet the declared schema."""


class CorpusIntegrityError(RuntimeError):
    """Existing write-once corpus material does not match its name/manifest."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n"
    )


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be a non-empty string")
    return value


def _require_timestamp(value: Any, name: str) -> str:
    result = _require_string(value, name)
    if "T" not in result:
        raise ValidationError(f"{name} must be an ISO-8601 timestamp with a UTC offset")
    candidate = result[:-1] + "+00:00" if result.endswith("Z") else result
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValidationError(f"{name} must be an ISO-8601 date or timestamp") from exc
    if parsed.tzinfo is None:
        raise ValidationError(f"{name} timestamps must include a UTC offset")
    return result


def _require_publication_date(value: Any, name: str) -> str:
    result = _require_string(value, name)
    candidate = result[:-1] + "+00:00" if result.endswith("Z") else result
    try:
        datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValidationError(f"{name} must be an ISO-8601 date or timestamp") from exc
    return result


def _require_url(value: Any, name: str) -> str:
    result = _require_string(value, name)
    parsed = urlsplit(result)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValidationError(f"{name} must be an absolute HTTP(S) URL")
    return result


def _identity_url(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def _publication_characteristics(value: str) -> tuple[str, bool]:
    if "T" not in value:
        return "date", False
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    return "timestamp", datetime.fromisoformat(candidate).tzinfo is not None


def _version_material(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        key: evidence.get(key)
        for key in ("classification", "metadata_fields", "text", "text_completeness")
        if key in evidence
    }


def _prepare_record(
    *,
    source_hash: str,
    source_byte_length: int,
    source_item_index: int,
    source_kind: str,
    article_id: str,
    canonical_url: str,
    publication_date: str,
    retrieved_at: str,
    evidence: dict[str, Any],
    raw_item_hash: str,
) -> dict[str, Any]:
    identity = _identity_url(canonical_url)
    evidence_hash = _sha256(_canonical_json(_version_material(evidence)))
    precision, timezone_known = _publication_characteristics(publication_date)
    record_seed = (
        f"{source_hash}:{source_item_index}:{source_kind}:{retrieved_at}".encode("utf-8")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": _sha256(record_seed),
        "source": {
            "sha256": source_hash,
            "byte_length": source_byte_length,
            "item_index": source_item_index,
            "raw_item_sha256": raw_item_hash,
            "source_kind": source_kind,
        },
        "article": {
            "article_id": article_id,
            "canonical_url": canonical_url,
            "identity_key": identity,
            "publication_date": publication_date,
            "publication_time_precision": precision,
            "publication_timezone_known": timezone_known,
        },
        "retrieval": {"retrieved_at": retrieved_at},
        "evidence": evidence,
        "evidence_sha256": evidence_hash,
    }


def _parse_nyt(raw: bytes, api: str, retrieved_at: str) -> list[dict[str, Any]]:
    if api not in NYT_SOURCE_KINDS:
        raise ValidationError(f"unsupported NYT API type: {api}")
    retrieved_at = _require_timestamp(retrieved_at, "retrieved_at")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("NYT input must be UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValidationError("NYT input must be a JSON object")
    response = payload.get("response")
    docs = response.get("docs") if isinstance(response, dict) else None
    if not isinstance(docs, list):
        raise ValidationError("NYT input must contain response.docs as an array")

    source_hash = _sha256(raw)
    records = []
    for index, doc in enumerate(docs):
        if not isinstance(doc, dict):
            raise ValidationError(f"response.docs[{index}] must be an object")
        article_id = _require_string(doc.get("_id") or doc.get("uri"), f"docs[{index}]._id")
        canonical_url = _require_url(doc.get("web_url"), f"docs[{index}].web_url")
        publication_date = _require_publication_date(
            doc.get("pub_date"), f"docs[{index}].pub_date"
        )
        metadata_fields = {
            name: doc[name]
            for name in ("abstract", "snippet", "lead_paragraph")
            if isinstance(doc.get(name), str)
        }
        headline = doc.get("headline")
        if isinstance(headline, dict):
            metadata_fields["headline"] = {
                key: value for key, value in headline.items() if isinstance(value, str)
            }
        elif isinstance(headline, str):
            metadata_fields["headline"] = headline
        evidence = {
            "classification": "metadata_only",
            "eligible_as_full_text": False,
            "text": None,
            "text_completeness": "metadata_only",
            "metadata_fields": metadata_fields,
        }
        raw_item = _canonical_json(doc)
        records.append(
            _prepare_record(
                source_hash=source_hash,
                source_byte_length=len(raw),
                source_item_index=index,
                source_kind=NYT_SOURCE_KINDS[api],
                article_id=article_id,
                canonical_url=canonical_url,
                publication_date=publication_date,
                retrieved_at=retrieved_at,
                evidence=evidence,
                raw_item_hash=_sha256(raw_item),
            )
        )
    if not records:
        raise ValidationError("NYT response.docs contains no records")
    return records


def _parse_full_text(raw: bytes) -> list[dict[str, Any]]:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("full-text input must be UTF-8 JSONL") from exc
    source_hash = _sha256(raw)
    records = []
    for line_number, line in enumerate(decoded.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"line {line_number} is not valid JSON") from exc
        if not isinstance(item, dict):
            raise ValidationError(f"line {line_number} must contain a JSON object")
        prefix = f"line {line_number}"
        if item.get("schema_version") != FULL_TEXT_SCHEMA_VERSION:
            raise ValidationError(
                f"{prefix}.schema_version must be {FULL_TEXT_SCHEMA_VERSION!r}"
            )
        source_kind = _require_string(item.get("source_kind"), f"{prefix}.source_kind")
        if source_kind not in FULL_TEXT_SOURCE_KINDS:
            raise ValidationError(
                f"{prefix}.source_kind must declare a user or publisher full-text export"
            )
        completeness = _require_string(
            item.get("text_completeness"), f"{prefix}.text_completeness"
        )
        if completeness not in COMPLETENESS_VALUES:
            raise ValidationError(
                f"{prefix}.text_completeness must be one of {sorted(COMPLETENESS_VALUES)}"
            )
        provenance = item.get("provenance")
        if not isinstance(provenance, dict):
            raise ValidationError(f"{prefix}.provenance must be an object")
        normalized_provenance = {
            field: _require_string(provenance.get(field), f"{prefix}.provenance.{field}")
            for field in sorted(PROVENANCE_FIELDS)
        }
        text = _require_string(item.get("text"), f"{prefix}.text")
        evidence = {
            "classification": "declared_full_text_export",
            "eligible_as_full_text": completeness == "complete",
            "text": text,
            "text_completeness": completeness,
            "completeness_basis": "submitter_declaration_unverified",
            "provenance": normalized_provenance,
        }
        raw_item = line.encode("utf-8")
        records.append(
            _prepare_record(
                source_hash=source_hash,
                source_byte_length=len(raw),
                source_item_index=line_number - 1,
                source_kind=source_kind,
                article_id=_require_string(item.get("article_id"), f"{prefix}.article_id"),
                canonical_url=_require_url(
                    item.get("canonical_url"), f"{prefix}.canonical_url"
                ),
                publication_date=_require_publication_date(
                    item.get("publication_date"), f"{prefix}.publication_date"
                ),
                retrieved_at=_require_timestamp(
                    item.get("retrieved_at"), f"{prefix}.retrieved_at"
                ),
                evidence=evidence,
                raw_item_hash=_sha256(raw_item),
            )
        )
    if not records:
        raise ValidationError("full-text JSONL input contains no records")
    return records


def _record_files(root: Path) -> Iterable[Path]:
    records = root / "records"
    return sorted(records.glob("*.json")) if records.exists() else []


def _load_records(root: Path) -> list[dict[str, Any]]:
    result = []
    for path in _record_files(root):
        raw = path.read_bytes()
        try:
            record = json.loads(raw)
            expected_id = _sha256(
                (
                    f"{record['source']['sha256']}:{record['source']['item_index']}:"
                    f"{record['source']['source_kind']}:{record['retrieval']['retrieved_at']}"
                ).encode(
                    "utf-8"
                )
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise CorpusIntegrityError(f"record is not valid JSON: {path}") from exc
        if path.stem != expected_id or record.get("record_id") != expected_id:
            raise CorpusIntegrityError(f"record filename does not match contents: {path}")
        if raw != _canonical_json(record):
            raise CorpusIntegrityError(f"record bytes are not canonical: {path}")
        expected_evidence_hash = _sha256(
            _canonical_json(_version_material(record.get("evidence", {})))
        )
        if record.get("evidence_sha256") != expected_evidence_hash:
            raise CorpusIntegrityError(f"record evidence hash does not match contents: {path}")
        result.append(record)
    return result


def _manifest(records: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(records, key=lambda row: row["record_id"])
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in ordered:
        key = (record["article"]["identity_key"], record["evidence"]["classification"])
        groups.setdefault(key, []).append(record)

    entries = []
    for record in ordered:
        group = groups[(record["article"]["identity_key"], record["evidence"]["classification"])]
        same = [r for r in group if r["evidence_sha256"] == record["evidence_sha256"]]
        different = [r for r in group if r["evidence_sha256"] != record["evidence_sha256"]]
        canonical_duplicate = min(r["record_id"] for r in same)
        entries.append(
            {
                "record_id": record["record_id"],
                "record_path": f"records/{record['record_id']}.json",
                "record_sha256": _sha256(_canonical_json(record)),
                "source": record["source"],
                "article": record["article"],
                "retrieval": record["retrieval"],
                "evidence_sha256": record["evidence_sha256"],
                "evidence_classification": record["evidence"]["classification"],
                "eligible_as_full_text": record["evidence"]["eligible_as_full_text"],
                "text_completeness": record["evidence"]["text_completeness"],
                "version_relations": {
                    "duplicate_of": (
                        canonical_duplicate if canonical_duplicate != record["record_id"] else None
                    ),
                    "has_conflict": bool(different),
                    "conflicting_record_ids": sorted(r["record_id"] for r in different),
                },
            }
        )
    sources: dict[str, dict[str, Any]] = {}
    for record in ordered:
        sha = record["source"]["sha256"]
        source = sources.setdefault(
            sha,
            {
                "sha256": sha,
                "byte_length": record["source"]["byte_length"],
                "path": f"sources/{sha}.source",
                "source_kinds": [],
            },
        )
        source["source_kinds"].append(record["source"]["source_kind"])
    for source in sources.values():
        source["source_kinds"] = sorted(set(source["source_kinds"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "deterministic": True,
        "record_count": len(entries),
        "source_count": len(sources),
        "sources": [sources[key] for key in sorted(sources)],
        "records": entries,
    }


def _ensure_private_dirs(root: Path) -> None:
    for path in (root, root / "sources", root / "records"):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.chmod(0o700)


def _write_once(path: Path, data: bytes) -> bool:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != data:
            raise CorpusIntegrityError(f"refusing to overwrite different bytes: {path}")
        return False
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)
    return True


def _write_manifest(root: Path, manifest: dict[str, Any]) -> None:
    data = _canonical_json(manifest)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".manifest-", dir=root)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, root / "manifest.json")
        (root / "manifest.json").chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _verify_existing(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    records = _load_records(root)
    for record in records:
        sha = record["source"]["sha256"]
        source_path = root / "sources" / f"{sha}.source"
        if not source_path.is_file() or _sha256(source_path.read_bytes()) != sha:
            raise CorpusIntegrityError(f"source bytes missing or changed: {source_path}")
    manifest_path = root / "manifest.json"
    if records or manifest_path.exists():
        expected = _canonical_json(_manifest(records))
        if not manifest_path.is_file() or manifest_path.read_bytes() != expected:
            raise CorpusIntegrityError("manifest does not match write-once records")
    return records


def _store(root: Path, raw: bytes, new_records: list[dict[str, Any]]) -> dict[str, Any]:
    _verify_existing(root)
    _ensure_private_dirs(root)
    source_hash = _sha256(raw)
    _write_once(root / "sources" / f"{source_hash}.source", raw)
    for record in new_records:
        _write_once(root / "records" / f"{record['record_id']}.json", _canonical_json(record))
    records = _load_records(root)
    manifest = _manifest(records)
    _write_manifest(root, manifest)
    return manifest


def import_nyt_metadata(
    input_path: Path | str,
    corpus_path: Path | str,
    *,
    api: str,
    retrieved_at: str,
) -> dict[str, Any]:
    raw = Path(input_path).read_bytes()
    records = _parse_nyt(raw, api, retrieved_at)
    return _store(Path(corpus_path), raw, records)


def import_full_text_jsonl(
    input_path: Path | str, corpus_path: Path | str
) -> dict[str, Any]:
    raw = Path(input_path).read_bytes()
    records = _parse_full_text(raw)
    return _store(Path(corpus_path), raw, records)
