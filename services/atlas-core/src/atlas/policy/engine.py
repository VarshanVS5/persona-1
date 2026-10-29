"""Policy engine: the authorization boundary (Master PRD 8.3, FR-06).

The LLM/planner is *not* an authority. A plan is only executable after it
passes, in order:

1. JSON-Schema validation against ``task-plan.schema.json``.
2. Allowlist check: every ``actionType`` must be registered in
   ``action-registry.json``. Unknown / blocked actions are rejected.
3. Per-action argument validation against the registry's ``argumentsSchema``
   (additionalProperties:false, required fields, allowlisted targets).
4. Risk-tier floor: a plan may not declare a tier *lower* than the registry's
   tier for that action (the model cannot down-rank a risky action).
5. Confirmation determination: the backend decides when human approval is
   required, independent of the plan's ``requiresConfirmation`` flag.

This module performs no I/O against the OS; it only decides. Execution happens
in ``atlas.executor`` and only for a ``PolicyDecision`` that ``allowed``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

from .contracts import (
    load_action_registry,
    load_task_plan_schema,
    plan_digest,
)
from .types import ActionStep, RiskTier, TaskPlan

# Risk tiers at or above this require explicit user confirmation.
CONFIRMATION_TIER_FLOOR = RiskTier.T2

# The blocked categories map to intent; any actionType matching a blocked
# prefix/name is rejected even if someone adds it to the plan. The registry's
# "blocked" list is the source of truth for human-readable reasons.
_BLOCKED_ACTION_HINTS = {
    "shell.exec",
    "shell.run",
    "cmd.exec",
    "powershell.exec",
    "credential.entry",
    "file.delete",
    "message.send",
    "payment.purchase",
    "security.settings_change",
    "security.uac_bypass",
}


class PolicyError(ValueError):
    """A plan (or step) violates policy and must not execute."""


@dataclass(frozen=True)
class StepDecision:
    stepId: int
    actionType: str
    allowed: bool
    effectiveRiskTier: RiskTier
    requiresConfirmation: bool
    reasons: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class PolicyDecision:
    """Result of validating a whole plan."""

    taskId: str
    allowed: bool
    requiresConfirmation: bool
    highestRiskTier: RiskTier
    planDigest: str
    steps: Sequence[StepDecision]
    reasons: Sequence[str] = field(default_factory=tuple)

    @property
    def rejectionSummary(self) -> str:
        return "; ".join(self.reasons) if self.reasons else ""


class PolicyEngine:
    """Stateless authorization boundary built from the frozen contracts."""

    def __init__(
        self,
        *,
        allowed_apps: Sequence[str] | None = None,
        registry: Mapping[str, Any] | None = None,
        plan_schema: Mapping[str, Any] | None = None,
    ) -> None:
        self._registry = dict(registry or load_action_registry())
        self._schema = dict(plan_schema or load_task_plan_schema())
        self._schema_validator = Draft202012Validator(self._schema)
        self._actions: dict[str, dict[str, Any]] = {
            a["actionType"]: a for a in self._registry.get("actions", [])
        }
        self._blocked_reasons: dict[str, str] = {
            b["category"]: b.get("reason", "Blocked by policy.")
            for b in self._registry.get("blocked", [])
        }
        # Case-insensitive, trimmed allowlist of app identifiers.
        self._allowed_apps = {a.strip().lower() for a in (allowed_apps or []) if a.strip()}

    # ---- public API -----------------------------------------------------

    def registered_action_types(self) -> set[str]:
        return set(self._actions)

    def validate_plan(self, plan_dict: Mapping[str, Any]) -> PolicyDecision:
        """Validate a plan (dict form, e.g. from the planner / a fixture)."""

        digest = plan_digest(plan_dict)

        schema_errors = self._schema_errors(plan_dict)
        if schema_errors:
            return PolicyDecision(
                taskId=str(plan_dict.get("taskId", "unknown")),
                allowed=False,
                requiresConfirmation=False,
                highestRiskTier=RiskTier.T0,
                planDigest=digest,
                steps=(),
                reasons=tuple(f"schema: {e}" for e in schema_errors),
            )

        plan = TaskPlan.from_dict(plan_dict)
        step_decisions = [self._decide_step(s) for s in plan.steps]

        reasons: list[str] = []
        if not plan.steps:
            reasons.append("plan has no steps")

        allowed = bool(plan.steps) and all(d.allowed for d in step_decisions)
        for d in step_decisions:
            if not d.allowed:
                reasons.extend(f"step {d.stepId}: {r}" for r in d.reasons)

        highest = max(
            (d.effectiveRiskTier for d in step_decisions),
            key=lambda t: t.level,
            default=RiskTier.T0,
        )
        requires_conf = allowed and (
            any(d.requiresConfirmation for d in step_decisions)
            or bool(plan.requiresConfirmation)
        )

        return PolicyDecision(
            taskId=plan.taskId,
            allowed=allowed,
            requiresConfirmation=requires_conf,
            highestRiskTier=highest,
            planDigest=digest,
            steps=tuple(step_decisions),
            reasons=tuple(reasons),
        )

    # ---- internals ------------------------------------------------------

    def _schema_errors(self, plan_dict: Mapping[str, Any]) -> list[str]:
        errors = sorted(self._schema_validator.iter_errors(plan_dict), key=lambda e: e.path)
        out: list[str] = []
        for e in errors:
            loc = "/".join(str(p) for p in e.path) or "<root>"
            out.append(f"{loc}: {e.message}")
        return out

    def _decide_step(self, step: ActionStep) -> StepDecision:
        reasons: list[str] = []
        action = self._actions.get(step.actionType)

        # 1. Blocked / unknown action types.
        if self._is_blocked(step.actionType):
            reason = self._blocked_reasons.get(
                step.actionType, "Action type is explicitly blocked by policy."
            )
            reasons.append(f"blocked action '{step.actionType}': {reason}")
        if action is None and not reasons:
            reasons.append(
                f"unknown action '{step.actionType}' is not in the action registry"
            )

        if action is None:
            # Nothing further can be validated for an unknown/blocked action.
            return StepDecision(
                stepId=step.stepId,
                actionType=step.actionType,
                allowed=False,
                effectiveRiskTier=step.riskTier,
                requiresConfirmation=True,
                reasons=tuple(reasons),
            )

        registry_tier = RiskTier(action["riskTier"])

        # 2. Risk-tier floor: the plan may not claim a lower tier than the
        #    registry. (Master PRD 12.4 / Common PRD 12: tiers cannot be
        #    lowered by model output.)
        if step.riskTier.level < registry_tier.level:
            reasons.append(
                f"risk tier '{step.riskTier.value}' is below the registry floor "
                f"'{registry_tier.value}' for '{step.actionType}' (tiers cannot be lowered)"
            )
        effective_tier = registry_tier if registry_tier.level >= step.riskTier.level else step.riskTier

        # 3. Argument validation against the registry's argumentsSchema.
        arg_errors = self._argument_errors(action, step.arguments)
        reasons.extend(arg_errors)

        # 4. Target allowlist (apps). Only enforced for actions that take appId.
        app_id = step.arguments.get("appId")
        if app_id is not None:
            if not isinstance(app_id, str) or app_id.strip().lower() not in self._allowed_apps:
                reasons.append(
                    f"app '{app_id}' is not in ATLAS_ALLOWED_APPS"
                )

        allowed = not reasons
        requires_conf = effective_tier.level >= CONFIRMATION_TIER_FLOOR.level

        return StepDecision(
            stepId=step.stepId,
            actionType=step.actionType,
            allowed=allowed,
            effectiveRiskTier=effective_tier,
            requiresConfirmation=requires_conf,
            reasons=tuple(reasons),
        )

    def _is_blocked(self, action_type: str) -> bool:
        if action_type in self._blocked_reasons:
            return True
        return action_type in _BLOCKED_ACTION_HINTS

    def _argument_errors(
        self, action: Mapping[str, Any], arguments: Mapping[str, Any]
    ) -> list[str]:
        schema = action.get("argumentsSchema")
        if not schema:
            return []
        validator = Draft202012Validator(schema)
        out: list[str] = []
        for e in sorted(validator.iter_errors(dict(arguments)), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in e.path) or "<arguments>"
            out.append(f"argument {loc}: {e.message}")
        return out
