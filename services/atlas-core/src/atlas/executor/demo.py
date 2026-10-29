"""Runnable Person 1 runtime demo (no UI, no network).

Demonstrates the one canonical path - policy -> confirmation -> execute ->
verify -> report - directly from the terminal, in mock or live mode.

Usage (from services/atlas-core):
    python -m atlas.executor.demo --plan ../../packages/contracts/examples/plan.valid.json
    python -m atlas.executor.demo --plan <file> --live --allowed-apps notepad,calc

In mock mode (default) no real process is launched. With --live on Windows it
launches the allowlisted app via the WindowsActionAdapter and verifies the
process exists. A plan requiring confirmation auto-approves with the reviewed
digest only when --yes is passed (so the confirmation gate is visible).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as a script without an installed package.
_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from atlas.executor.factory import build_runtime  # noqa: E402
from atlas.policy.types import TaskStatus  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ATLAS Person 1 runtime demo")
    parser.add_argument("--plan", required=True, help="Path to a TaskPlan JSON file")
    parser.add_argument("--live", action="store_true", help="Use the real Windows adapter")
    parser.add_argument("--allowed-apps", default="notepad,calc", help="Comma list (ATLAS_ALLOWED_APPS)")
    parser.add_argument("--yes", action="store_true", help="Auto-approve if confirmation is required")
    args = parser.parse_args(argv)

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    apps = [a.strip() for a in args.allowed_apps.split(",") if a.strip()]
    mode = "LIVE (real Windows actions)" if args.live else "MOCK (no real actions)"
    print(f"== ATLAS runtime demo | mode: {mode} | allowed apps: {apps} ==")

    emitted: list[dict] = []

    def sink(ev: dict) -> None:
        emitted.append(ev)
        print(f"  event: {ev['type']:<22} {json.dumps(ev['payload'])}")

    runtime = build_runtime(mock=not args.live, allowed_apps=apps, event_sink=sink)

    outcome = runtime.run(plan)
    if outcome.status is TaskStatus.AWAITING_CONFIRMATION:
        if not args.yes:
            print("\nConfirmation required. Re-run with --yes to approve the reviewed plan.")
            return 10
        decision = runtime._policy.validate_plan(plan)  # recompute reviewed digest
        print(f"\nApproving reviewed plan digest {decision.planDigest}")
        outcome = runtime.run(plan, approved_digest=decision.planDigest)

    print(f"\n== Result: {outcome.status.value} ==")
    if outcome.reason:
        print(f"   reason: {outcome.reason}")
    for s in outcome.steps:
        print(f"   step {s.stepId} {s.actionType}: {s.status.value} ({s.failureCode.value}) {s.detail}")

    return 0 if outcome.status is TaskStatus.SUCCEEDED else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
