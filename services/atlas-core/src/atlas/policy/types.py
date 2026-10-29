"""Typed runtime models for the ATLAS desktop runtime (Person 1).

These dataclasses mirror the **frozen** shared contracts in
``packages/contracts/`` (``task-plan.schema.json``, ``action-registry.json``,
``events.schema.json``). The project owner owns ``atlas.models`` and the
contract files; this module is an internal, owner-contract-faithful
representation used only by the Person 1 runtime modules
(``policy``/``executor``/``adapters``/``verifier``/``journal``) so they can run
and be tested today without editing files owned by others.

If/when the project owner publishes ``atlas.models``, these types are intended
to be replaced by (or adapted to) that module. Field names and the ``RiskTier``
/ ``TaskStatus`` enumerations match the contracts exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class RiskTier(str, Enum):
    """Master PRD section 7. Ordered; a higher value is more dangerous."""

    T0 = "T0"  # read-only inspection
    T1 = "T1"  # narrow, low-impact action
    T2 = "T2"  # broad / potentially disruptive mutation
    T3 = "T3"  # irreversible / external / credential / security-sensitive

    @property
    def level(self) -> int:
        return {"T0": 0, "T1": 1, "T2": 2, "T3": 3}[self.value]


class TaskStatus(str, Enum):
    """Common PRD 4.2 / events.schema.json TaskStatus."""

    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    CANCELLING = "CANCELLING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Condition:
    """A pre/postcondition (task-plan.schema.json $defs/Condition)."""

    type: str
    args: Mapping[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "Condition":
        return Condition(type=str(data["type"]), args=dict(data.get("args", {})))


@dataclass(frozen=True)
class ActionStep:
    """task-plan.schema.json $defs/ActionStep."""

    stepId: int
    actionType: str
    arguments: Mapping[str, Any]
    riskTier: RiskTier
    preconditions: Sequence[Condition]
    postconditions: Sequence[Condition]
    timeoutMs: int
    idempotencyKey: str

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "ActionStep":
        return ActionStep(
            stepId=int(data["stepId"]),
            actionType=str(data["actionType"]),
            arguments=dict(data.get("arguments", {})),
            riskTier=RiskTier(data["riskTier"]),
            preconditions=[Condition.from_dict(c) for c in data.get("preconditions", [])],
            postconditions=[Condition.from_dict(c) for c in data.get("postconditions", [])],
            timeoutMs=int(data["timeoutMs"]),
            idempotencyKey=str(data["idempotencyKey"]),
        )


@dataclass(frozen=True)
class TaskPlan:
    """task-plan.schema.json TaskPlan."""

    taskId: str
    userRequest: str
    summary: str
    requiresConfirmation: bool
    steps: Sequence[ActionStep]

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "TaskPlan":
        return TaskPlan(
            taskId=str(data["taskId"]),
            userRequest=str(data["userRequest"]),
            summary=str(data["summary"]),
            requiresConfirmation=bool(data["requiresConfirmation"]),
            steps=[ActionStep.from_dict(s) for s in data.get("steps", [])],
        )
