"""Condition verification (Master PRD FR-08).

A task is successful only when its machine-checkable postconditions pass
against *observed* state. The verifier never trusts a narrative; it asks the
adapter for observations and evaluates the condition types declared in the
plan / action registry.

Supported condition types (prototype):
- ``app.allowlisted``: the app is within ATLAS_ALLOWED_APPS (precondition).
- ``window.exists``: a window/process for the app is observable (postcondition).

Unknown condition types fail *closed* (treated as unverifiable, not passed) so
a plan cannot smuggle an always-true condition the runtime does not understand.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from ..policy.types import Condition

ObserveFn = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class CheckResult:
    conditionType: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    checks: Sequence[CheckResult]

    @property
    def firstFailure(self) -> CheckResult | None:
        for c in self.checks:
            if not c.passed:
                return c
        return None


class Verifier:
    """Evaluates conditions using an adapter's observations + the app allowlist."""

    def __init__(self, *, allowed_apps: Sequence[str] | None = None) -> None:
        self._allowed_apps = {a.strip().lower() for a in (allowed_apps or []) if a.strip()}

    def _check(
        self,
        condition: Condition,
        action_type: str,
        arguments: Mapping[str, Any],
        observe: ObserveFn,
    ) -> CheckResult:
        ctype = condition.type

        if ctype == "app.allowlisted":
            app_id = self._arg_value(condition, arguments, "appId", "argument")
            ok = isinstance(app_id, str) and app_id.strip().lower() in self._allowed_apps
            return CheckResult(ctype, ok, f"app '{app_id}' allowlisted={ok}")

        if ctype == "window.exists":
            obs = observe(action_type, arguments)
            ok = bool(obs.get("windowExists"))
            how = obs.get("verifiedBy", "observation")
            return CheckResult(ctype, ok, f"window.exists={ok} via {how}")

        # Fail closed on anything we do not understand.
        return CheckResult(ctype, False, f"unsupported condition type '{ctype}' (fail-closed)")

    @staticmethod
    def _arg_value(
        condition: Condition, arguments: Mapping[str, Any], key: str, indirect_key: str
    ) -> Any:
        """Resolve a condition's target value.

        The registry sometimes references an *argument name* (e.g.
        ``{"argument": "appId"}``) and the plan examples sometimes inline the
        value (e.g. ``{"appId": "notepad"}``). Support both.
        """

        if key in condition.args:
            return condition.args[key]
        if indirect_key in condition.args:
            return arguments.get(str(condition.args[indirect_key]))
        return None

    def verify(
        self,
        conditions: Sequence[Condition],
        action_type: str,
        arguments: Mapping[str, Any],
        observe: ObserveFn,
    ) -> VerificationResult:
        checks = [self._check(c, action_type, arguments, observe) for c in conditions]
        # An empty condition list verifies vacuously true; callers decide
        # whether that is acceptable for a given risk tier.
        return VerificationResult(passed=all(c.passed for c in checks), checks=checks)
