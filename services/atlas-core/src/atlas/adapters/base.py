"""Adapter protocol, result types, and the runtime failure taxonomy.

An *adapter* performs a single registered action against the Windows desktop
(or a safe fake). Adapters never decide authorization - the policy engine does
that first. An adapter reports *observations*, never a narrative "success".
Verification of postconditions is done separately by ``atlas.verifier`` using
the observation an adapter exposes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable


class FailureCode(str, Enum):
    """Failure taxonomy (Person 1 deliverable; Master PRD 14 adversarial cases).

    These codes are stable and safe to surface in events (no secrets).
    """

    OK = "OK"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    TARGET_MISSING = "TARGET_MISSING"            # app/window/control not found
    TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"        # more than one plausible target
    STALE_SELECTOR = "STALE_SELECTOR"            # previously-resolved target gone
    NOT_ALLOWLISTED = "NOT_ALLOWLISTED"          # app/path outside approved scope
    LAUNCH_FAILED = "LAUNCH_FAILED"              # OS could not start the process
    UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"    # adapter does not implement it
    ADAPTER_ERROR = "ADAPTER_ERROR"             # unexpected adapter-internal error
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    POSTCONDITION_FAILED = "POSTCONDITION_FAILED"


@dataclass(frozen=True)
class ActionResult:
    """Outcome of one adapter invocation.

    ``observations`` carries machine-checkable facts the verifier uses (e.g.
    ``{"windowExists": True, "pids": [1234]}``). It must never contain secrets.
    """

    code: FailureCode
    detail: str = ""
    observations: Mapping[str, Any] = field(default_factory=dict)
    compensation: Mapping[str, Any] | None = None  # recorded inverse, if safe

    @property
    def ok(self) -> bool:
        return self.code is FailureCode.OK


class AdapterError(RuntimeError):
    """Raised for adapter-internal faults; executor converts to ADAPTER_ERROR."""


class CancelledError(RuntimeError):
    """Raised when a cooperative cancellation is observed mid-action."""


@runtime_checkable
class ActionAdapter(Protocol):
    """Interface every adapter implements.

    ``supports`` lets the executor pick the adapter for an ``actionType``.
    ``execute`` must be cooperative with ``is_cancelled`` (a zero-arg callable
    returning bool) and must respect ``timeout_s``.
    """

    name: str

    def supports(self, action_type: str) -> bool: ...

    def execute(
        self,
        action_type: str,
        arguments: Mapping[str, Any],
        *,
        timeout_s: float,
        is_cancelled,
    ) -> ActionResult: ...

    def observe(self, action_type: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return current observations for pre/postcondition checks."""
        ...
