"""OWNER: Person 1 - Desktop Runtime & Safety. Do not edit without owner approval.

Allowlist and risk policy: only registered actions; reject unsupported
paths/apps/actions (FR-06). This package is the authorization boundary between
untrusted planner output and the execution runtime (Master PRD 8.3).
"""

from .contracts import (
    ContractError,
    contracts_dir,
    load_action_registry,
    load_events_schema,
    load_task_plan_schema,
    plan_digest,
)
from .engine import (
    CONFIRMATION_TIER_FLOOR,
    PolicyDecision,
    PolicyEngine,
    PolicyError,
    StepDecision,
)
from .types import ActionStep, Condition, RiskTier, TaskPlan, TaskStatus

__all__ = [
    "ActionStep",
    "CONFIRMATION_TIER_FLOOR",
    "Condition",
    "ContractError",
    "PolicyDecision",
    "PolicyEngine",
    "PolicyError",
    "RiskTier",
    "StepDecision",
    "TaskPlan",
    "TaskStatus",
    "contracts_dir",
    "load_action_registry",
    "load_events_schema",
    "load_task_plan_schema",
    "plan_digest",
]
