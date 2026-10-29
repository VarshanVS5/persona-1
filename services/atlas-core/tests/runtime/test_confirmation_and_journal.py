"""Confirmation binding and journal redaction tests.

Covers: confirmation applies to the exact reviewed plan digest; a changed plan
is rejected; secrets never appear in the journal.
"""

from __future__ import annotations

import copy

from atlas.adapters.fake import FakeActionAdapter
from atlas.executor.runtime import ExecutionRuntime
from atlas.journal.ledger import Journal, redact
from atlas.policy.engine import PolicyEngine
from atlas.policy.types import TaskStatus
from atlas.verifier.checks import Verifier

T2_PLAN = {
    "taskId": "task-conf-1",
    "userRequest": "Open editor (high risk variant)",
    "summary": "Requires confirmation.",
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
            "idempotencyKey": "task-conf-1-step-1",
        }
    ],
}


def build(apps=("notepad",), journal=None):
    apps = list(apps)
    events: list[dict] = []
    rt = ExecutionRuntime(
        policy=PolicyEngine(allowed_apps=apps),
        verifier=Verifier(allowed_apps=apps),
        journal=journal or Journal(),
        adapters=[FakeActionAdapter()],
        event_sink=events.append,
    )
    return rt, events


def test_confirmation_required_without_approval():
    rt, events = build()
    outcome = rt.run(T2_PLAN)
    assert outcome.status is TaskStatus.AWAITING_CONFIRMATION
    conf = [e for e in events if e["type"] == "confirmation_required"]
    assert conf and conf[0]["payload"]["planDigest"].startswith("sha256:")


def test_approval_with_matching_digest_executes():
    rt, _ = build()
    decision = rt._policy.validate_plan(T2_PLAN)  # digest the user "reviewed"
    outcome = rt.run(T2_PLAN, approved_digest=decision.planDigest)
    assert outcome.status is TaskStatus.SUCCEEDED


def test_approval_with_stale_digest_is_rejected():
    rt, _ = build()
    changed = copy.deepcopy(T2_PLAN)
    changed["summary"] = "a different plan the user did not review"
    outcome = rt.run(changed, approved_digest="sha256:deadbeef")
    assert outcome.status is TaskStatus.FAILED
    assert "does not match" in outcome.reason


def test_journal_redacts_secrets():
    data = {
        "api_key": "sk-abcdef0123456789abcdef",
        "nested": {"password": "hunter2", "note": "Authorization: Bearer abc.def.ghi"},
        "safe": "notepad",
    }
    red = redact(data)
    assert red["api_key"] == "***REDACTED***"
    assert red["nested"]["password"] == "***REDACTED***"
    assert "Bearer" not in red["nested"]["note"] or "REDACTED" in red["nested"]["note"]
    assert red["safe"] == "notepad"


def test_journal_entries_have_no_raw_secrets():
    journal = Journal()
    rt, _ = build(journal=journal)
    decision = rt._policy.validate_plan(T2_PLAN)
    rt.run(T2_PLAN, approved_digest=decision.planDigest)
    # Simulate a step recording that includes a secret-looking arg.
    journal.record("task-conf-1", "custom", {"token": "sk-shouldnotappear1234567890"})
    blob = "\n".join(str(e.data) for e in journal.entries())
    assert "sk-shouldnotappear1234567890" not in blob
