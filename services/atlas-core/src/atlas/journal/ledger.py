"""Execution ledger / audit journal with secret redaction (FR-11, FR-10).

The journal records task state transitions, action decisions, consent,
verification results, durations, and errors. It is append-only and redacts
likely secrets before writing (Master PRD 12 "Redact secrets from logs and
errors"). It can write JSON Lines to a file and/or keep entries in memory
(used by tests and by the orchestrator to build the GET /tasks/{id} response).
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

# Keys whose values are always redacted regardless of content.
_SECRET_KEY_PATTERN = re.compile(
    r"(api[_-]?key|secret|password|passwd|pwd|token|authorization|auth|"
    r"bearer|credential|cookie|session|private[_-]?key)",
    re.IGNORECASE,
)

# Value patterns that look like secrets (bearer tokens, long hex/base64 blobs).
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),            # common key prefix style
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),              # AWS access key id
    re.compile(r"\b[A-Fa-f0-9]{40,}\b"),              # long hex blob
)

_REDACTED = "***REDACTED***"


def redact(value: Any) -> Any:
    """Recursively redact likely secrets from arbitrary JSON-ish data."""

    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and _SECRET_KEY_PATTERN.search(k):
                out[k] = _REDACTED
            else:
                out[k] = redact(v)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        redacted = value
        for pat in _SECRET_VALUE_PATTERNS:
            redacted = pat.sub(_REDACTED, redacted)
        return redacted
    return value


@dataclass
class JournalEntry:
    taskId: str
    kind: str                       # e.g. "decision", "step", "verification", "status"
    timestamp: str                  # ISO-8601 UTC
    data: Mapping[str, Any] = field(default_factory=dict)


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Journal:
    """Append-only, redacting execution ledger. Thread-safe."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else None
        self._entries: list[JournalEntry] = []
        self._lock = threading.Lock()
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, task_id: str, kind: str, data: Mapping[str, Any] | None = None) -> JournalEntry:
        entry = JournalEntry(
            taskId=task_id,
            kind=kind,
            timestamp=_utc_now(),
            data=redact(dict(data or {})),
        )
        with self._lock:
            self._entries.append(entry)
            if self._path:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        return entry

    def entries(self, task_id: str | None = None) -> Sequence[JournalEntry]:
        with self._lock:
            if task_id is None:
                return list(self._entries)
            return [e for e in self._entries if e.taskId == task_id]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
