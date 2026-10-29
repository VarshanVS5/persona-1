"""Policy engine tests (authorization boundary).

Covers acceptance items: only registered actions can execute; unsupported
paths/apps/actions are rejected; risk tiers cannot be lowered.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.policy import PolicyEngine, RiskTier

CONTRACTS = Path(__file__).resolve().parents[4] / "packages" / "contracts"
EXAMPLES = CONTRACTS / "examples"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


@pytest.fixture
def engine(allowed_apps):
    return PolicyEngine(allowed_apps=allowed_apps)


def test_valid_plan_is_allowed(engine):
    decision = engine.validate_plan(load_example("plan.valid.json"))
    assert decision.allowed is True
    assert decision.highestRiskTier == RiskTier.T1
    # app.open is T1 (< T2 floor) so no confirmation from tier; but the plan
    # itself sets requiresConfirmation=true, which the engine honours.
    assert decision.requiresConfirmation is True
    assert decision.planDigest.startswith("sha256:")


def test_unknown_action_is_rejected(engine):
    decision = engine.validate_plan(load_example("plan.invalid-unknown-action.json"))
    assert decision.allowed is False
    assert any("shell.exec" in r for r in decision.reasons)


def test_lowered_risk_tier_is_rejected(engine):
    decision = engine.validate_plan(load_example("plan.invalid-lowered-risk.json"))
    assert decision.allowed is False
    assert any("below the registry floor" in r for r in decision.reasons)


def test_app_not_in_allowlist_is_rejected():
    engine = PolicyEngine(allowed_apps=["calc"])  # notepad NOT allowed
    decision = engine.validate_plan(load_example("plan.valid.json"))
    assert decision.allowed is False
    assert any("ATLAS_ALLOWED_APPS" in r for r in decision.reasons)


def test_schema_invalid_plan_is_rejected(engine):
    bad = {"taskId": "x", "userRequest": "y", "summary": "z", "requiresConfirmation": False}
    decision = engine.validate_plan(bad)  # missing "steps"
    assert decision.allowed is False
    assert any(r.startswith("schema:") for r in decision.reasons)


def test_bad_arguments_are_rejected(engine):
    plan = load_example("plan.valid.json")
    plan["steps"][0]["arguments"] = {"appId": "notepad", "extra": "nope"}  # additionalProperties
    decision = engine.validate_plan(plan)
    assert decision.allowed is False
    assert any("argument" in r for r in decision.reasons)


def test_empty_plan_rejected(engine):
    plan = load_example("plan.valid.json")
    plan["steps"] = []
    decision = engine.validate_plan(plan)
    assert decision.allowed is False
    assert any("no steps" in r for r in decision.reasons)
