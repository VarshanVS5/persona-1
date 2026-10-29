"""Live Windows adapter smoke test (opt-in).

This test performs a REAL action (launches notepad) and verifies the process
via psutil, then terminates it. It is skipped unless:
  - the host is Windows, and
  - ATLAS_RUN_LIVE_TESTS=1 is set (so CI / headless runs do not spawn windows).

Run it explicitly on a Windows desktop:
    $env:ATLAS_RUN_LIVE_TESTS="1"; python -m pytest tests/runtime/test_windows_live.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

from atlas.adapters.windows import WindowsActionAdapter

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win") or os.environ.get("ATLAS_RUN_LIVE_TESTS") != "1",
    reason="live Windows test: set ATLAS_RUN_LIVE_TESTS=1 on a Windows desktop to run",
)


def test_live_app_open_notepad_and_cleanup():
    adapter = WindowsActionAdapter()
    try:
        result = adapter.execute(
            "app.open", {"appId": "notepad"}, timeout_s=10.0, is_cancelled=lambda: False
        )
        assert result.ok, f"expected OK, got {result.code}: {result.detail}"
        assert result.observations.get("windowExists") is True
        assert result.observations.get("verifiedBy")  # recorded how it was verified
    finally:
        # Terminate any notepad we launched so the test is self-cleaning.
        try:
            import psutil

            for p in psutil.process_iter(["pid", "name"]):
                if (p.info.get("name") or "").lower() == "notepad.exe":
                    p.terminate()
        except Exception:
            pass
