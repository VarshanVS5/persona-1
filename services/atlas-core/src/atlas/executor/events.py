"""Builders for contract-shaped AtlasEvent envelopes (events.schema.json).

Every event includes ``schemaVersion`` ("1.0"), ``taskId``, ``timestamp`` and a
typed ``payload``. Events never carry secrets (the journal redactor is applied
to any free-form data before it reaches an event). The executor emits these via
a sink callback so the orchestrator/UI (Person 3) can forward them over SSE.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_event(task_id: str, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "taskId": task_id,
        "timestamp": _timestamp(),
        "type": event_type,
        "payload": dict(payload),
    }
