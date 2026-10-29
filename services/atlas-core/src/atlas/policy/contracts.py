"""Loading of the frozen shared contracts and a stable plan digest.

Person 1 consumes ``packages/contracts/`` read-only (see workstream
INSTRUCTIONS section 5-6). This module locates those files, loads the action
registry and the JSON Schemas, and computes a deterministic digest over a plan
so that confirmation can be bound to the *exact* reviewed plan
(api-contract.md: a plan is never silently replaced between review and
execution).
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping


class ContractError(RuntimeError):
    """Raised when the shared contracts cannot be located or parsed."""


def find_contracts_dir(start: Path | None = None) -> Path:
    """Walk upward from ``start`` to locate ``packages/contracts``.

    Works from the installed package location or from a test run regardless of
    the current working directory.
    """

    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / "packages" / "contracts"
        if (candidate / "action-registry.json").is_file():
            return candidate
    raise ContractError(
        "Could not locate packages/contracts/action-registry.json by walking up "
        f"from {here}. Set ATLAS_CONTRACTS_DIR or run from within the repo."
    )


@lru_cache(maxsize=1)
def _contracts_dir_cached() -> Path:
    import os

    override = os.environ.get("ATLAS_CONTRACTS_DIR")
    if override:
        d = Path(override)
        if not (d / "action-registry.json").is_file():
            raise ContractError(f"ATLAS_CONTRACTS_DIR={override} has no action-registry.json")
        return d
    return find_contracts_dir()


def contracts_dir() -> Path:
    return _contracts_dir_cached()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - defensive
        raise ContractError(f"Missing contract file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"Malformed contract file {path}: {exc}") from exc


def load_action_registry() -> dict[str, Any]:
    return _load_json(contracts_dir() / "action-registry.json")


def load_task_plan_schema() -> dict[str, Any]:
    return _load_json(contracts_dir() / "task-plan.schema.json")


def load_events_schema() -> dict[str, Any]:
    return _load_json(contracts_dir() / "events.schema.json")


def plan_digest(plan: Mapping[str, Any]) -> str:
    """Return a stable SHA-256 digest of a plan (dict form).

    Canonical JSON (sorted keys, no insignificant whitespace) ensures the same
    plan always yields the same digest. ``confirm`` must echo this value.
    """

    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
