"""Persistence utilities for source-to-target link records.

This module intentionally focuses on durable storage only.
It does not watch files, trigger regeneration, or prompt users.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path

SCHEMA_VERSION = 1
LINK_FILE_NAME = ".resume-links.json"

TARGET_TYPE_TEX = "tex"
TARGET_TYPE_PDF = "pdf"

TARGET_STATE_ACTIVE = "active"
TARGET_STATE_MISSING = "missing"
TARGET_STATE_REMOVED = "removed"
TARGET_STATE_INVALID = "invalid"

VALID_TARGET_TYPES = {TARGET_TYPE_TEX, TARGET_TYPE_PDF}
VALID_TARGET_STATES = {
    TARGET_STATE_ACTIVE,
    TARGET_STATE_MISSING,
    TARGET_STATE_REMOVED,
    TARGET_STATE_INVALID
}


@dataclass
class LinkedTarget:
    """Persisted metadata for a linked target output file."""

    path: str
    target_type: str
    state: str = TARGET_STATE_ACTIVE
    last_generated_at: str | None = None
    last_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "target_type": self.target_type,
            "state": self.state,
            "last_generated_at": self.last_generated_at,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "LinkedTarget | None":
        path = raw.get("path")
        target_type = raw.get("target_type")
        if not isinstance(path, str) or not isinstance(target_type, str):
            return None

        target_type = target_type.lower().strip()
        if target_type not in VALID_TARGET_TYPES:
            return None

        state = str(raw.get("state") or TARGET_STATE_ACTIVE).lower().strip()
        if state not in VALID_TARGET_STATES:
            state = TARGET_STATE_INVALID

        last_generated_at = raw.get("last_generated_at")
        if last_generated_at is not None and not isinstance(last_generated_at, str):
            last_generated_at = None

        last_error = raw.get("last_error")
        if last_error is not None and not isinstance(last_error, str):
            last_error = None

        return cls(
            path=_normalize_abs(path),
            target_type=target_type,
            state=state,
            last_generated_at=last_generated_at,
            last_error=last_error,
        )


@dataclass
class SourceLinkRecord:
    """Per-source persisted record stored in .resume-links.json."""

    source_path: str
    source_last_seen_mtime: float | None = None
    source_last_seen_size: int | None = None
    updated_at: str | None = None
    targets: list[LinkedTarget] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "source": {
                "path": self.source_path,
                "last_seen_mtime": self.source_last_seen_mtime,
                "last_seen_size": self.source_last_seen_size,
            },
            "targets": [target.to_dict() for target in self.targets],
            "updated_at": self.updated_at,
        }

    @classmethod
    def empty_for_source(cls, source_path: str) -> "SourceLinkRecord":
        source_abs = _normalize_abs(source_path)
        mtime, size = _source_stat(source_abs)
        return cls(
            source_path=source_abs,
            source_last_seen_mtime=mtime,
            source_last_seen_size=size,
            updated_at=_utc_now_iso(),
            targets=[],
        )

    @classmethod
    def from_payload(cls, source_path: str, data: dict) -> "SourceLinkRecord":
        source_abs = _normalize_abs(source_path)

        raw_source = data.get("source", {})
        if not isinstance(raw_source, dict):
            raw_source = {}

        raw_mtime = raw_source.get("last_seen_mtime")
        source_last_seen_mtime = float(raw_mtime) if isinstance(raw_mtime, (int, float)) else None

        raw_size = raw_source.get("last_seen_size")
        source_last_seen_size = int(raw_size) if isinstance(raw_size, (int, float)) else None

        updated_at = data.get("updated_at")
        if not isinstance(updated_at, str):
            updated_at = None

        targets: list[LinkedTarget] = []
        raw_targets = data.get("targets", [])
        if isinstance(raw_targets, list):
            for raw in raw_targets:
                if not isinstance(raw, dict):
                    continue
                target = LinkedTarget.from_dict(raw)
                if target is not None:
                    targets.append(target)

        return cls(
            source_path=source_abs,
            source_last_seen_mtime=source_last_seen_mtime,
            source_last_seen_size=source_last_seen_size,
            updated_at=updated_at,
            targets=targets,
        )


def _normalize_abs(path: str) -> str:
    return str(Path(path).expanduser().resolve(strict=False))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _source_stat(path: str) -> tuple[float | None, int | None]:
    try:
        stat = os.stat(path)
        return float(stat.st_mtime), int(stat.st_size)
    except OSError:
        return None, None


def get_link_file_path(source_path: str) -> str:
    """Return the per-source metadata path for linked outputs."""
    source_abs = _normalize_abs(source_path)
    return str(Path(source_abs).parent / LINK_FILE_NAME)


def load_source_links(source_path: str) -> SourceLinkRecord:
    """Load source link metadata. Missing/corrupt files return an empty record."""
    source_abs = _normalize_abs(source_path)
    mtime, size = _source_stat(source_abs)
    link_file_path = get_link_file_path(source_abs)

    if not os.path.exists(link_file_path):
        return SourceLinkRecord.empty_for_source(source_abs)

    try:
        with open(link_file_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return SourceLinkRecord.empty_for_source(source_abs)

    if not isinstance(payload, dict):
        return SourceLinkRecord.empty_for_source(source_abs)

    record = SourceLinkRecord.from_payload(source_abs, payload)
    if record.source_last_seen_mtime is None:
        record.source_last_seen_mtime = mtime
    if record.source_last_seen_size is None:
        record.source_last_seen_size = size
    if record.updated_at is None:
        record.updated_at = _utc_now_iso()
    return record


def save_source_links(record: SourceLinkRecord) -> str:
    """Persist link metadata atomically and return the metadata file path."""
    source_abs = _normalize_abs(record.source_path)
    record.source_path = source_abs
    record.source_last_seen_mtime, record.source_last_seen_size = _source_stat(source_abs)
    record.updated_at = _utc_now_iso()

    link_file = Path(get_link_file_path(source_abs))
    link_file.parent.mkdir(parents=True, exist_ok=True)

    payload = record.to_dict()
    tmp_path = str(link_file) + ".tmp"

    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")

    os.replace(tmp_path, link_file)
    return str(link_file)


def record_target_link(
    source_path: str,
    target_path: str,
    target_type: str,
    generated_at: str | None = None,
) -> SourceLinkRecord:
    """Add or update a target link for a source and persist immediately."""
    target_type_norm = str(target_type).lower().strip()
    if target_type_norm not in VALID_TARGET_TYPES:
        raise ValueError(f"Unsupported target type: {target_type}")

    source_abs = _normalize_abs(source_path)
    target_abs = _normalize_abs(target_path)
    generated_at = generated_at or _utc_now_iso()

    record = load_source_links(source_abs)

    found = False
    for target in record.targets:
        if target.path == target_abs:
            target.target_type = target_type_norm
            target.state = TARGET_STATE_ACTIVE
            target.last_generated_at = generated_at
            target.last_error = None
            found = True
            break

    if not found:
        record.targets.append(
            LinkedTarget(
                path=target_abs,
                target_type=target_type_norm,
                state=TARGET_STATE_ACTIVE,
                last_generated_at=generated_at,
                last_error=None,
            )
        )

    save_source_links(record)
    return record


def update_target_state(
    source_path: str,
    target_path: str,
    state: str,
    last_error: str | None = None,
) -> SourceLinkRecord:
    """Update a target state for future move/delete workflows and persist."""
    state_norm = str(state).lower().strip()
    if state_norm not in VALID_TARGET_STATES:
        raise ValueError(f"Unsupported target state: {state}")

    source_abs = _normalize_abs(source_path)
    target_abs = _normalize_abs(target_path)
    record = load_source_links(source_abs)

    for target in record.targets:
        if target.path == target_abs:
            target.state = state_norm
            target.last_error = last_error
            break
    else:
        raise ValueError(f"Target is not linked for source: {target_abs}")

    save_source_links(record)
    return record


def remove_target_link(source_path: str, target_path: str) -> SourceLinkRecord:
    """Remove a target link from a source and persist."""
    source_abs = _normalize_abs(source_path)
    target_abs = _normalize_abs(target_path)
    record = load_source_links(source_abs)

    record.targets = [target for target in record.targets if target.path != target_abs]
    save_source_links(record)
    return record
