"""End-to-end runtime tests using the fake adapter (mock mode).

Covers acceptance items: preconditions/postconditions checked; failure does not
become success; cancellation prevents future steps; timeout, missing target,
stale selector, and duplicate request.
"""

from __future__ import annotations

import copy

import pytest

from atlas.adapters.fake import FakeActionAdapter, FakeBehaviour
from atlas.executor.runtime import ExecutionRuntime
from atlas.journal.ledger import Journal
from atlas.policy.engine import PolicyEngine
from atlas.policy.types import TaskStatus
from atlas.verifier.checks import Verifier

VALID_PLAN = {
    "taskId": "task-rt-1",
    "userRequest": "Open my editor",
    "summary": "Open the allowlisted editor application.",
    "requiresConfirmation": False,
    "steps": [
        {
            "stepId": 1,
            "actionType": "app.open",
            "arguments": {"appId": "notepad"},
            "riskTier": "T1",
            "preconditions": [{"type": "app.allowlisted", "args": {"appId": "notepad"}}],
            "postconditions": [{"type": "window.exists", "args": {"appId": "notepad"}}],
            "timeoutMs": 2000,
            "idempotencyKey": "task-rt-1-step-1",
        }
    ],
}


def build(fake: FakeActionAdapter, apps=("notepad", "calc")):
    apps = list(apps)
    events: list[dict] = []
    rt = ExecutionRuntime(
        policy=PolicyEngine(allowed_apps=apps),
        verifier=Verifier(allowed_apps=apps),
        journal=Journal(),
        adapters=[fake],
        event_sink=events.append,
    )
    return rt, events


def plan_with(**overrides):
    p = copy.deepcopy(VALID_PLAN)
    p.update(overrides)
    return p


def test_happy_path_succeeds_and_verifies():
    fake = FakeActionAdapter()
    rt, events = build(fake)
    outcome = rt.run(VALID_PLAN)
    assert outcome.status is TaskStatus.SUCCEEDED
    types = [e["type"] for e in events]
    assert "step_started" in types
    assert "verification_passed" in types
    assert "task_completed" in types


def test_postcondition_failure_is_not_success():
    # Window never appears -> postcondition window.exists fails.
    fake = FakeActionAdapter({"notepad": FakeBehaviour(window_appears=False)})
    rt, events = build(fake)
    outcome = rt.run(VALID_PLAN)
    assert outcome.status is TaskStatus.FAILED
    assert "postcondition failed" in outcome.reason
    assert "task_completed" not in [e["type"] for e in events]


def test_launch_failure_is_reported_as_failure():
    fake = FakeActionAdapter({"notepad": FakeBehaviour(launch_fails=True)})
    rt, _ = build(fake)
    outcome = rt.run(VALID_PLAN)
    assert outcome.status is TaskStatus.FAILED
    assert outcome.steps[0].failureCode.value == "LAUNCH_FAILED"


def test_timeout_is_reported():
    # open_delay longer than the 2000ms timeout and the adapter returns TIMEOUT.
    fake = FakeActionAdapter({"notepad": FakeBehaviour(open_delay_s=5.0)})
    rt, _ = build(fake)
    plan = plan_with()
    plan["steps"][0]["timeoutMs"] = 200
    outcome = rt.run(plan)
    assert outcome.status is TaskStatus.FAILED
    assert outcome.steps[0].failureCode.value == "TIMEOUT"


def test_cancellation_prevents_future_steps():
    fake = FakeActionAdapter()
    rt, events = build(fake)
    outcome = rt.run(VALID_PLAN, is_cancelled=lambda: True)
    assert outcome.status is TaskStatus.CANCELLED
    assert "task_cancelled" in [e["type"] for e in events]
    assert not any(e["type"] == "verification_passed" for e in events)


def test_missing_target_appid():
    fake = FakeActionAdapter()
    rt, _ = build(fake)
    plan = plan_with()
    # Schema requires appId; to hit the adapter's TARGET_MISSING we must keep
    # policy happy, so test the adapter path via an allowlisted-but-blank id is
    # not possible. Instead assert policy rejects an empty-arg plan.
    plan["steps"][0]["arguments"] = {}
    outcome = rt.run(plan)
    assert outcome.status is TaskStatus.FAILED  # rejected by policy (required appId)


def test_stale_selector_window_vanishes():
    # window appears during execute() but is closed before postcondition check.
    fake = FakeActionAdapter({"notepad": FakeBehaviour(window_appears=True)})
    rt, _ = build(fake)

    original_execute = fake.execute

    def execute_then_close(action_type, arguments, *, timeout_s, is_cancelled):
        res = original_execute(action_type, arguments, timeout_s=timeout_s, is_cancelled=is_cancelled)
        fake.force_close(str(arguments.get("appId", "")))  # external close -> stale
        return res

    fake.execute = execute_then_close  # type: ignore[assignment]
    outcome = rt.run(VALID_PLAN)
    assert outcome.status is TaskStatus.FAILED
    assert "postcondition failed" in outcome.reason


def test_duplicate_idempotency_key_is_suppressed():
    fake = FakeActionAdapter()
    rt, _ = build(fake)
    first = rt.run(VALID_PLAN)
    assert first.status is TaskStatus.SUCCEEDED
    # Re-running the SAME plan (same idempotencyKey) must not re-execute.
    second = rt.run(VALID_PLAN)
    assert second.status is TaskStatus.FAILED
    assert "duplicate request" in second.steps[0].detail


def test_rejected_plan_never_executes():
    fake = FakeActionAdapter()
    rt, events = build(fake)
    bad = plan_with(taskId="task-rt-bad")
    bad["steps"][0]["actionType"] = "shell.exec"
    outcome = rt.run(bad)
    assert outcome.status is TaskStatus.FAILED
    assert "task_completed" not in [e["type"] for e in events]
