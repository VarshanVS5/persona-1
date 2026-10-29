"""Real Windows adapter for ``app.open`` (Master PRD FR-07, 9.1).

Scope is intentionally tiny and safe for the prototype: launch one of a small
set of **allowlisted** desktop apps by a symbolic ``appId`` and confirm the
process exists. We resolve ``appId`` to an executable from an internal map plus
``shutil.which`` - we never accept an arbitrary path from the plan, so model
output cannot cause an arbitrary executable to run.

Window verification: for the prototype we verify the launched **process**
exists and is running (via ``psutil``). Full semantic UI-Automation window
checks (``uiautomation``/pywinauto) are a documented follow-up (see
workstream failure taxonomy / known limitations); we do not claim they are
implemented. If ``psutil`` is unavailable we fall back to checking the Popen
handle, and we say so in the detail string rather than faking success.

On non-Windows hosts this adapter refuses to execute (NOT the mock): callers
should use the fake adapter in mock mode.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from typing import Any, Mapping

from .base import ActionResult, CancelledError, FailureCode

try:  # psutil is optional at import time; required for real verification.
    import psutil  # type: ignore
except Exception:  # pragma: no cover - environment dependent
    psutil = None  # type: ignore


# Symbolic appId -> candidate executable names. Only these may be launched.
# Keys are matched case-insensitively against ATLAS_ALLOWED_APPS membership
# (the policy engine already enforced the allowlist before we run).
_APP_EXECUTABLES: dict[str, tuple[str, ...]] = {
    "notepad": ("notepad.exe",),
    "calc": ("calc.exe",),
    "mspaint": ("mspaint.exe",),
    "wordpad": ("wordpad.exe", "write.exe"),
    "code": ("code.cmd", "code.exe", "code"),  # VS Code, if on PATH
    "explorer": ("explorer.exe",),
}

# Process image names we expect per app, used to verify via psutil.
_APP_PROCESS_NAMES: dict[str, tuple[str, ...]] = {
    "notepad": ("notepad.exe",),
    "calc": ("calc.exe", "calculatorapp.exe", "applicationframehost.exe"),
    "mspaint": ("mspaint.exe",),
    "wordpad": ("wordpad.exe", "write.exe"),
    "code": ("code.exe",),
    "explorer": ("explorer.exe",),
}


class WindowsActionAdapter:
    """Launches allowlisted Windows apps and verifies via process state."""

    name = "windows"

    def __init__(self, *, process_names: Mapping[str, tuple[str, ...]] | None = None) -> None:
        self._process_names = dict(process_names or _APP_PROCESS_NAMES)
        self._launched: dict[str, int] = {}  # appId -> pid of our launch

    def supports(self, action_type: str) -> bool:
        return action_type == "app.open"

    @staticmethod
    def is_windows() -> bool:
        return sys.platform.startswith("win")

    def _resolve_executable(self, app_id: str) -> str | None:
        candidates = _APP_EXECUTABLES.get(app_id.lower())
        if not candidates:
            return None
        for name in candidates:
            found = shutil.which(name)
            if found:
                return found
            # Common Windows system apps live under System32 and are on PATH,
            # but guard for environments where which() misses them.
            system32 = os.path.join(os.environ.get("SystemRoot", r"C:\\Windows"), "System32", name)
            if os.path.isfile(system32):
                return system32
        return None

    def execute(
        self,
        action_type: str,
        arguments: Mapping[str, Any],
        *,
        timeout_s: float,
        is_cancelled,
    ) -> ActionResult:
        if action_type != "app.open":
            return ActionResult(FailureCode.UNSUPPORTED_ACTION, f"windows adapter cannot do {action_type}")
        if not self.is_windows():
            return ActionResult(
                FailureCode.ADAPTER_ERROR,
                "WindowsActionAdapter requires Windows; use the fake adapter in mock mode",
            )

        app_id = str(arguments.get("appId", "")).strip()
        if not app_id:
            return ActionResult(FailureCode.TARGET_MISSING, "no appId provided")

        exe = self._resolve_executable(app_id)
        if exe is None:
            return ActionResult(
                FailureCode.TARGET_MISSING,
                f"no known executable for app '{app_id}' on this machine",
            )

        if is_cancelled():
            raise CancelledError("cancelled before launch")

        try:
            # No shell=True: we pass an explicit, resolved executable path only.
            proc = subprocess.Popen([exe], close_fds=True)
        except (OSError, ValueError) as exc:
            return ActionResult(FailureCode.LAUNCH_FAILED, f"could not launch '{app_id}': {exc}")

        self._launched[app_id.lower()] = proc.pid

        # Poll until the window/process is observable or the timeout elapses.
        deadline = time.monotonic() + timeout_s
        while True:
            if is_cancelled():
                raise CancelledError("cancelled during launch verification")
            obs = self.observe(action_type, arguments)
            if obs.get("windowExists"):
                return ActionResult(
                    FailureCode.OK,
                    f"launched '{app_id}' ({os.path.basename(exe)})",
                    observations=obs,
                )
            if time.monotonic() >= deadline:
                return ActionResult(
                    FailureCode.TIMEOUT,
                    f"'{app_id}' did not become observable within {timeout_s:.1f}s",
                    observations=obs,
                )
            time.sleep(0.1)

    def observe(self, action_type: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        app_id = str(arguments.get("appId", "")).strip().lower()
        expected = self._process_names.get(app_id, (app_id + ".exe",))
        launched_pid = self._launched.get(app_id)

        if psutil is None:
            # Degraded verification: report honestly that we cannot confirm.
            return {
                "windowExists": launched_pid is not None,
                "verifiedBy": "popen-handle-only (psutil unavailable)",
                "pids": [launched_pid] if launched_pid else [],
            }

        pids: list[int] = []
        expected_lower = {n.lower() for n in expected}
        for p in psutil.process_iter(["pid", "name"]):
            try:
                pname = (p.info.get("name") or "").lower()
            except Exception:  # pragma: no cover - race during iteration
                continue
            if pname in expected_lower:
                pids.append(p.info["pid"])

        return {
            "windowExists": bool(pids),
            "verifiedBy": "psutil-process-scan",
            "pids": pids,
        }
