"""Stable runtime assembly for the orchestrator and Person 4 (QA/integration).

``build_runtime`` is the one entry point other modules should call to get a
fully wired ``ExecutionRuntime``. It selects the adapter by mode:

- mock mode (``mock=True``): the clearly-labelled ``FakeActionAdapter`` only.
  Safe on any OS; performs no real desktop actions.
- live mode (``mock=False``): the real ``WindowsActionAdapter`` plus the fake
  adapter as a fallback for action types the Windows adapter does not support.

The allowlist (``allowed_apps``) comes from the project owner's config
(ATLAS_ALLOWED_APPS). Until ``atlas.config`` is implemented we accept it as an
argument and also read ATLAS_ALLOWED_APPS from the environment as a fallback so
the runtime is usable today.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from ..adapters.fake import FakeActionAdapter
from ..adapters.windows import WindowsActionAdapter
from ..journal.ledger import Journal
from ..policy.engine import PolicyEngine
from ..verifier.checks import Verifier
from .runtime import ExecutionRuntime


def resolve_allowed_apps(allowed_apps: Sequence[str] | None) -> list[str]:
    if allowed_apps:
        return list(allowed_apps)
    raw = os.environ.get("ATLAS_ALLOWED_APPS", "")
    return [a.strip() for a in raw.split(",") if a.strip()]


def build_runtime(
    *,
    mock: bool = True,
    allowed_apps: Sequence[str] | None = None,
    journal_path: str | Path | None = None,
    event_sink=None,
) -> ExecutionRuntime:
    apps = resolve_allowed_apps(allowed_apps)
    policy = PolicyEngine(allowed_apps=apps)
    verifier = Verifier(allowed_apps=apps)
    journal = Journal(journal_path)

    if mock:
        adapters = [FakeActionAdapter()]
    else:
        adapters = [WindowsActionAdapter(), FakeActionAdapter()]

    return ExecutionRuntime(
        policy=policy,
        verifier=verifier,
        journal=journal,
        adapters=adapters,
        event_sink=event_sink,
    )
