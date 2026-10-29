"""Execution runtime (Master PRD FR-06..FR-11).

``ExecutionRuntime`` is the one canonical path from a validated, approved plan
to verified desktop actions. It:

- refuses to run a plan the policy engine rejected (defence in depth);
- enforces confirmation: a plan that requires approval will not execute unless
  ``approved_digest`` matches the exact reviewed plan digest;
- runs one step at a time, each in a worker thread bounded by the step's
  ``timeoutMs``, cooperatively cancellable;
- checks preconditions before and postconditions after each step, from real
  observations (never assumed success);
- prevents duplicate execution via ``idempotencyKey`` (a timed-out step is not
  blindly replayed - Master PRD 8.3);
- emits contract-shaped events and writes a redacted journal;
- reports SUCCEEDED / FAILED / PARTIAL / CANCELLED honestly.

It takes the policy engine, a verifier, a journal, and one or more adapters by
dependency injection, so the fake adapter (mock mode) and the Windows adapter
are interchangeable.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from ..adapters.base import ActionResult, CancelledError, FailureCode
from ..journal.ledger import Journal
from ..policy.engine import PolicyDecision, PolicyEngine
from ..policy.types import ActionStep, TaskPlan, TaskStatus
from ..verifier.checks import Verifier
from .events import make_event

EventSink = Callable[[Mapping[str, Any]], None]


@dataclass
class StepOutcome:
    stepId: int
    actionType: str
    status: TaskStatus
    failureCode: FailureCode
    detail: str = ""
    observations: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class TaskOutcome:
    taskId: str
    status: TaskStatus
    steps: Sequence[StepOutcome] = field(default_factory=list)
    reason: str = ""
    failedStepId: int | None = None
    events: Sequence[Mapping[str, Any]] = field(default_factory=list)


class ExecutionRuntime:
    def __init__(
        self,
        *,
        policy: PolicyEngine,
        verifier: Verifier,
        journal: Journal,
        adapters: Sequence[Any],
        event_sink: EventSink | None = None,
    ) -> None:
        self._policy = policy
        self._verifier = verifier
        self._journal = journal
        self._adapters = list(adapters)
        self._external_sink = event_sink
        self._seen_idempotency_keys: set[str] = set()
        self._lock = threading.Lock()

    # ---- adapter routing ------------------------------------------------

    def _adapter_for(self, action_type: str):
        for a in self._adapters:
            if a.supports(action_type):
                return a
        return None

    # ---- public entry point --------------------------------------------

    def run(
        self,
        plan_dict: Mapping[str, Any],
        *,
        approved_digest: str | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> TaskOutcome:
        events: list[Mapping[str, Any]] = []
        is_cancelled = is_cancelled or (lambda: False)

        def emit(event_type: str, payload: Mapping[str, Any]) -> None:
            ev = make_event(str(plan_dict.get("taskId", "unknown")), event_type, payload)
            events.append(ev)
            self._journal.record(ev["taskId"], f"event:{event_type}", payload)
            if self._external_sink:
                self._external_sink(ev)

        decision = self._policy.validate_plan(plan_dict)
        task_id = decision.taskId

        self._journal.record(
            task_id,
            "decision",
            {
                "allowed": decision.allowed,
                "requiresConfirmation": decision.requiresConfirmation,
                "highestRiskTier": decision.highestRiskTier.value,
                "planDigest": decision.planDigest,
                "reasons": list(decision.reasons),
            },
        )

        # 1. Policy rejection -> never execute.
        if not decision.allowed:
            emit("task_failed", {"status": TaskStatus.FAILED.value, "reason": decision.rejectionSummary})
            return TaskOutcome(
                taskId=task_id,
                status=TaskStatus.FAILED,
                reason=decision.rejectionSummary or "plan rejected by policy",
                events=events,
            )

        # 2. Confirmation enforcement bound to the exact reviewed digest.
        if decision.requiresConfirmation:
            if approved_digest is None:
                emit(
                    "confirmation_required",
                    {"planDigest": decision.planDigest, "highestRiskTier": decision.highestRiskTier.value},
                )
                return TaskOutcome(
                    taskId=task_id,
                    status=TaskStatus.AWAITING_CONFIRMATION,
                    reason="user confirmation required",
                    events=events,
                )
            if approved_digest != decision.planDigest:
                reason = "approval digest does not match the reviewed plan (plan changed)"
                emit("task_failed", {"status": TaskStatus.FAILED.value, "reason": reason})
                return TaskOutcome(task_id, TaskStatus.FAILED, reason=reason, events=events)

        plan = TaskPlan.from_dict(plan_dict)
        return self._execute_steps(plan, decision, emit, is_cancelled, events)

    # ---- step loop ------------------------------------------------------

    def _execute_steps(
        self,
        plan: TaskPlan,
        decision: PolicyDecision,
        emit: Callable[[str, Mapping[str, Any]], None],
        is_cancelled: Callable[[], bool],
        events: list[Mapping[str, Any]],
    ) -> TaskOutcome:
        outcomes: list[StepOutcome] = []
        any_succeeded = False

        for step in plan.steps:
            # Cancellation checked before every step (FR-09): no new step starts.
            if is_cancelled():
                emit("task_cancelled", {"status": TaskStatus.CANCELLED.value, "reason": "cancelled before step"})
                return TaskOutcome(
                    plan.taskId, TaskStatus.PARTIAL if any_succeeded else TaskStatus.CANCELLED,
                    steps=outcomes, reason="cancelled before step", events=events,
                )

            outcome = self._run_step(plan.taskId, step, emit, is_cancelled)
            outcomes.append(outcome)

            if outcome.status is TaskStatus.SUCCEEDED:
                any_succeeded = True
                continue

            if outcome.status is TaskStatus.CANCELLED:
                return TaskOutcome(
                    plan.taskId, TaskStatus.PARTIAL if any_succeeded else TaskStatus.CANCELLED,
                    steps=outcomes, reason=outcome.detail, failedStepId=step.stepId, events=events,
                )

            # Any failure stops the task (onFailure: stop_and_report).
            status = TaskStatus.PARTIAL if any_succeeded else TaskStatus.FAILED
            emit("task_failed", {"status": status.value, "reason": outcome.detail, "failedStepId": step.stepId})
            return TaskOutcome(
                plan.taskId, status, steps=outcomes, reason=outcome.detail,
                failedStepId=step.stepId, events=events,
            )

        emit("task_completed", {"status": TaskStatus.SUCCEEDED.value})
        return TaskOutcome(plan.taskId, TaskStatus.SUCCEEDED, steps=outcomes, events=events)

    def _run_step(
        self,
        task_id: str,
        step: ActionStep,
        emit: Callable[[str, Mapping[str, Any]], None],
        is_cancelled: Callable[[], bool],
    ) -> StepOutcome:
        # Idempotency / duplicate-request prevention (FR + Master PRD 12).
        with self._lock:
            if step.idempotencyKey in self._seen_idempotency_keys:
                detail = f"duplicate request suppressed (idempotencyKey={step.idempotencyKey})"
                self._journal.record(task_id, "idempotency.skip", {"stepId": step.stepId})
                emit("verification_failed", {
                    "stepId": step.stepId, "actionType": step.actionType,
                    "reason": detail, "status": TaskStatus.FAILED.value,
                })
                return StepOutcome(step.stepId, step.actionType, TaskStatus.FAILED, FailureCode.ADAPTER_ERROR, detail)
            self._seen_idempotency_keys.add(step.idempotencyKey)

        adapter = self._adapter_for(step.actionType)
        if adapter is None:
            detail = f"no adapter supports '{step.actionType}'"
            emit("verification_failed", {
                "stepId": step.stepId, "actionType": step.actionType,
                "reason": detail, "status": TaskStatus.FAILED.value,
            })
            return StepOutcome(step.stepId, step.actionType, TaskStatus.FAILED, FailureCode.UNSUPPORTED_ACTION, detail)

        emit("step_started", {"stepId": step.stepId, "actionType": step.actionType, "status": TaskStatus.RUNNING.value})

        # Preconditions.
        pre = self._verifier.verify(step.preconditions, step.actionType, step.arguments, adapter.observe)
        if not pre.passed:
            fail = pre.firstFailure
            detail = f"precondition failed: {fail.detail if fail else 'unknown'}"
            emit("verification_failed", {
                "stepId": step.stepId, "actionType": step.actionType,
                "reason": detail, "status": TaskStatus.FAILED.value,
            })
            return StepOutcome(step.stepId, step.actionType, TaskStatus.FAILED, FailureCode.PRECONDITION_FAILED, detail)

        # Execute with timeout + cancellation in a worker thread.
        result = self._execute_with_timeout(adapter, step, is_cancelled)

        if result.code is FailureCode.CANCELLED:
            emit("task_cancelled", {"status": TaskStatus.CANCELLING.value, "reason": result.detail})
            return StepOutcome(step.stepId, step.actionType, TaskStatus.CANCELLED, FailureCode.CANCELLED, result.detail, result.observations)

        if not result.ok:
            emit("verification_failed", {
                "stepId": step.stepId, "actionType": step.actionType,
                "reason": f"{result.code.value}: {result.detail}", "status": TaskStatus.FAILED.value,
            })
            return StepOutcome(step.stepId, step.actionType, TaskStatus.FAILED, result.code, result.detail, result.observations)

        # Postconditions from real observations (FR-08).
        emit("step_started", {"stepId": step.stepId, "actionType": step.actionType, "status": TaskStatus.VERIFYING.value})
        post = self._verifier.verify(step.postconditions, step.actionType, step.arguments, adapter.observe)
        if not post.passed:
            fail = post.firstFailure
            detail = f"postcondition failed: {fail.detail if fail else 'unknown'}"
            emit("verification_failed", {
                "stepId": step.stepId, "actionType": step.actionType,
                "reason": detail, "status": TaskStatus.FAILED.value,
            })
            return StepOutcome(step.stepId, step.actionType, TaskStatus.FAILED, FailureCode.POSTCONDITION_FAILED, detail, result.observations)

        self._journal.record(task_id, "verification", {
            "stepId": step.stepId, "checks": [c.__dict__ for c in post.checks],
        })
        emit("verification_passed", {"stepId": step.stepId, "actionType": step.actionType, "status": TaskStatus.SUCCEEDED.value})
        return StepOutcome(step.stepId, step.actionType, TaskStatus.SUCCEEDED, FailureCode.OK, result.detail, result.observations)

    def _execute_with_timeout(
        self, adapter: Any, step: ActionStep, is_cancelled: Callable[[], bool]
    ) -> ActionResult:
        timeout_s = max(step.timeoutMs, 1) / 1000.0
        box: dict[str, ActionResult] = {}

        def worker() -> None:
            try:
                box["result"] = adapter.execute(
                    step.actionType, step.arguments, timeout_s=timeout_s, is_cancelled=is_cancelled
                )
            except CancelledError as exc:
                box["result"] = ActionResult(FailureCode.CANCELLED, str(exc))
            except Exception as exc:  # defensive: adapter faults never crash runtime
                box["result"] = ActionResult(FailureCode.ADAPTER_ERROR, f"{type(exc).__name__}: {exc}")

        t = threading.Thread(target=worker, name=f"atlas-step-{step.stepId}", daemon=True)
        t.start()
        # Give the worker the step budget plus a small grace period to return a
        # cooperative TIMEOUT itself; if it overruns we report TIMEOUT and move
        # on (we never blindly retry a possibly-successful action).
        t.join(timeout_s + 0.5)
        if t.is_alive():
            return ActionResult(
                FailureCode.TIMEOUT,
                f"step {step.stepId} ('{step.actionType}') exceeded {timeout_s:.1f}s and did not return",
            )
        return box.get("result", ActionResult(FailureCode.ADAPTER_ERROR, "adapter produced no result"))
