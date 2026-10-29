"""Every event the runtime emits must validate against events.schema.json.

This is the contract guarantee Person 3 (UI) and Person 4 (QA) rely on.
"""

from __future__ import annotations

from jsonschema import Draft202012Validator, RefResolver

from atlas.adapters.fake import FakeActionAdapter, FakeBehaviour
from atlas.executor.runtime import ExecutionRuntime
from atlas.journal.ledger import Journal
from atlas.policy.contracts import (
    contracts_dir,
    load_events_schema,
    load_task_plan_schema,
)
from atlas.policy.engine import PolicyEngine
from atlas.verifier.checks import Verifier

PLAN = {
    "taskId": "task-ev-1",
    "userRequest": "Open my editor",
    "summary": "Open the allowlisted editor application.",
    "requiresConfirmation": True,
    "steps": [
        {
            "stepId": 1,
            "actionType": "app.open",
            "arguments": {"appId": "notepad"},
            "riskTier": "T1",
            "preconditions": [{"type": "app.allowlisted", "args": {"appId": "notepad"}}],
            "postconditions": [{"type": "window.exists", "args": {"appId": "notepad"}}],
            "timeoutMs": 2000,
            "idempotencyKey": "task-ev-1-step-1",
        }
    ],
}


def _event_validator() -> Draft202012Validator:
    schema = load_events_schema()
    # Resolve the "$ref": "task-plan.schema.json" sibling reference.
    base = contracts_dir().as_uri() + "/"
    store = {
        schema["$id"]: schema,
        "https://project-atlas.local/contracts/task-plan.schema.json": load_task_plan_schema(),
    }
    resolver = RefResolver(base_uri=base, referrer=schema, store=store)
    return Draft202012Validator(schema, resolver=resolver)


def _run_and_collect() -> list[dict]:
    events: list[dict] = []
    apps = ["notepad"]
    rt = ExecutionRuntime(
        policy=PolicyEngine(allowed_apps=apps),
        verifier=Verifier(allowed_apps=apps),
        journal=Journal(),
        adapters=[FakeActionAdapter()],
        event_sink=events.append,
    )
    decision = rt._policy.validate_plan(PLAN)
    rt.run(PLAN, approved_digest=decision.planDigest)
    return events


def test_all_emitted_events_validate():
    validator = _event_validator()
    events = _run_and_collect()
    assert events, "expected at least one event"
    for ev in events:
        errors = sorted(validator.iter_errors(ev), key=lambda e: list(e.path))
        assert not errors, f"event {ev['type']} invalid: {[e.message for e in errors]}"


def test_failure_path_events_validate():
    validator = _event_validator()
    events: list[dict] = []
    apps = ["notepad"]
    rt = ExecutionRuntime(
        policy=PolicyEngine(allowed_apps=apps),
        verifier=Verifier(allowed_apps=apps),
        journal=Journal(),
        adapters=[FakeActionAdapter({"notepad": FakeBehaviour(window_appears=False)})],
        event_sink=events.append,
    )
    decision = rt._policy.validate_plan(PLAN)
    rt.run(PLAN, approved_digest=decision.planDigest)
    assert any(e["type"] == "verification_failed" for e in events)
    for ev in events:
        errors = sorted(validator.iter_errors(ev), key=lambda e: list(e.path))
        assert not errors, f"event {ev['type']} invalid: {[e.message for e in errors]}"
