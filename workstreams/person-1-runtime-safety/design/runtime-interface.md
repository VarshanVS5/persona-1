# Person 1 runtime interface (stable surface for the orchestrator & Person 4)

The orchestrator (project owner) and QA (Person 4) integrate with the runtime
through one assembly function and one `run` call. Everything else is internal.

## Assembly

```python
from atlas.executor import build_runtime

runtime = build_runtime(
    mock=True,                        # True = FakeActionAdapter only (safe anywhere)
    allowed_apps=["notepad", "calc"],  # from ATLAS_ALLOWED_APPS
    journal_path=None,                 # optional JSONL audit file
    event_sink=my_sink,                # callable(event_dict) -> None, e.g. SSE push
)
```

`event_sink` receives contract-shaped `AtlasEvent` dicts
(`events.schema.json`), already redacted. Forward them to the UI over SSE.

## Running a plan

```python
outcome = runtime.run(plan_dict, approved_digest=None, is_cancelled=lambda: False)
```

- `plan_dict`: a `TaskPlan` (dict) from Person 2's planner or a
  `packages/contracts/examples/plan.*.json` fixture.
- `approved_digest`: the `planDigest` from the `confirmation_required` /
  `plan_ready` event, echoed by `POST /confirm`. Required only when the plan
  needs confirmation.
- `is_cancelled`: a zero-arg callable the executor polls before each step and
  cooperatively during each action; wire it to `POST /cancel`.

### Return value (`TaskOutcome`)

| field | meaning |
|---|---|
| `status` | `TaskStatus` enum: `SUCCEEDED` / `FAILED` / `PARTIAL` / `CANCELLED` / `AWAITING_CONFIRMATION` |
| `steps` | per-step `StepOutcome` (id, actionType, status, failureCode, detail, observations) |
| `reason` | human-readable failure/rejection summary (secret-free) |
| `failedStepId` | the step that stopped the task, if any |
| `events` | the ordered list of events emitted during the call |

## Flow enforced inside `run`

1. `PolicyEngine.validate_plan` — schema, allowlist, risk-tier floor, args,
   app allowlist. Rejected -> `task_failed`, no execution.
2. Confirmation — if required and no matching `approved_digest`:
   `confirmation_required` + `AWAITING_CONFIRMATION` (stops).
3. Per step: `step_started` -> preconditions -> adapter `execute`
   (timeout + cancel) -> postconditions -> `verification_passed` /
   `verification_failed`.
4. Terminal: `task_completed` / `task_failed` / `task_cancelled`.

## Mapping to the REST contract (`docs/api-contract.md`)

- `POST /tasks/plan` -> orchestrator calls `runtime.run(plan)`; relay events.
- `POST /tasks/{id}/confirm` -> orchestrator re-calls `runtime.run(plan,
  approved_digest=body.planDigest)`.
- `POST /tasks/{id}/cancel` -> flip the `is_cancelled` flag for that task.
- `GET /tasks/{id}` -> build from `outcome` + `journal.entries(task_id)`.

The runtime does not own the HTTP layer, task registry, or SSE transport (those
are the project owner's `api/`+`orchestrator/`). It is transport-agnostic.
