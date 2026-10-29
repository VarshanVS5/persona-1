"""Deterministic fake adapter for tests and mock mode.

CLEARLY LABELLED MOCK - this adapter performs **no** OS actions. It simulates
launching an allowlisted app by recording state in memory, so the runtime,
policy, verifier, journal, cancellation, and timeout logic can be tested
deterministically without touching the real desktop (Common PRD section 6;
mock mode must be safe and explicit).

Behaviour is driven by a small script so tests can inject timeouts, missing
targets, and stale selectors.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from .base import ActionResult, CancelledError, FailureCode


@dataclass
class FakeBehaviour:
    """Per-app scripted behaviour for the fake adapter."""

    open_delay_s: float = 0.0        # simulate work (to exercise timeout/cancel)
    launch_fails: bool = False       # simulate the OS refusing to launch
    window_appears: bool = True      # whether window.exists becomes true
    stale_after_open: bool = False   # window vanishes before verification


class FakeActionAdapter:
    """In-memory simulation of ``app.open``. MOCK - no real processes."""

    name = "fake"

    def __init__(self, behaviours: Mapping[str, FakeBehaviour] | None = None) -> None:
        self._behaviours: dict[str, FakeBehaviour] = dict(behaviours or {})
        self._open_apps: set[str] = set()

    def set_behaviour(self, app_id: str, behaviour: FakeBehaviour) -> None:
        self._behaviours[app_id.lower()] = behaviour

    def supports(self, action_type: str) -> bool:
        return action_type == "app.open"

    def _behaviour(self, app_id: str) -> FakeBehaviour:
        return self._behaviours.get(app_id.lower(), FakeBehaviour())

    def execute(
        self,
        action_type: str,
        arguments: Mapping[str, Any],
        *,
        timeout_s: float,
        is_cancelled,
    ) -> ActionResult:
        if action_type != "app.open":
            return ActionResult(FailureCode.UNSUPPORTED_ACTION, f"fake adapter cannot do {action_type}")

        app_id = str(arguments.get("appId", "")).strip()
        if not app_id:
            return ActionResult(FailureCode.TARGET_MISSING, "no appId provided")

        behaviour = self._behaviour(app_id)

        # Cooperative wait that honours cancellation and the timeout budget.
        deadline = time.monotonic() + timeout_s
        step = 0.01
        waited = 0.0
        while waited < behaviour.open_delay_s:
            if is_cancelled():
                raise CancelledError("cancelled during fake open")
            if time.monotonic() >= deadline:
                return ActionResult(
                    FailureCode.TIMEOUT,
                    f"fake open of '{app_id}' exceeded {timeout_s:.1f}s",
                )
            time.sleep(min(step, behaviour.open_delay_s - waited))
            waited += step

        if behaviour.launch_fails:
            return ActionResult(FailureCode.LAUNCH_FAILED, f"fake launch of '{app_id}' failed")

        if behaviour.window_appears and not behaviour.stale_after_open:
            self._open_apps.add(app_id.lower())

        return ActionResult(
            FailureCode.OK,
            f"fake-opened '{app_id}'",
            observations={"windowExists": app_id.lower() in self._open_apps, "mock": True},
            compensation={"actionType": "app.close", "appId": app_id, "note": "mock only"},
        )

    def observe(self, action_type: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        app_id = str(arguments.get("appId", "")).strip().lower()
        return {"windowExists": app_id in self._open_apps, "mock": True}

    # Test helper to simulate an external close (stale selector).
    def force_close(self, app_id: str) -> None:
        self._open_apps.discard(app_id.lower())
