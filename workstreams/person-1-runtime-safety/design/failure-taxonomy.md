# Runtime failure taxonomy (Person 1)

Stable, secret-free codes emitted by the runtime. Source of truth:
`services/atlas-core/src/atlas/adapters/base.py` (`FailureCode`). These map to
the contract events in `packages/contracts/events.schema.json`.

| Code | Meaning | Where raised | Event / status |
|---|---|---|---|
| `OK` | Action completed and is verifiable | adapter `execute` | `verification_passed` |
| `TIMEOUT` | Step exceeded `timeoutMs` (no blind retry) | executor / adapter | `verification_failed` -> `FAILED`/`PARTIAL` |
| `CANCELLED` | Cooperative cancel observed | executor / adapter | `task_cancelled` -> `CANCELLED`/`PARTIAL` |
| `TARGET_MISSING` | App/window/control not found | adapter | `verification_failed` |
| `TARGET_AMBIGUOUS` | More than one plausible target (reserved; not hit by `app.open`) | adapter | `verification_failed` |
| `STALE_SELECTOR` | Previously-resolved target gone before verify | verifier (postcondition) | `verification_failed` |
| `NOT_ALLOWLISTED` | App/path outside approved scope | policy (pre-exec) | `task_failed` (never executes) |
| `LAUNCH_FAILED` | OS could not start the process | adapter | `verification_failed` |
| `UNSUPPORTED_ACTION` | No adapter implements the action | executor | `verification_failed` |
| `ADAPTER_ERROR` | Unexpected adapter fault / duplicate idempotency key | executor | `verification_failed` |
| `PRECONDITION_FAILED` | A precondition did not hold | verifier | `verification_failed` |
| `POSTCONDITION_FAILED` | Postcondition not observed (failure != success) | verifier | `verification_failed` |

## Rejection vs failure

- **Rejected** (policy): the plan never executes. No adapter is invoked. Causes:
  schema invalid, unknown/blocked action, lowered risk tier, bad arguments,
  app not in `ATLAS_ALLOWED_APPS`, empty plan.
- **Failed** (runtime): the plan was allowed and (if required) approved, but a
  step did not verify. Reported as `FAILED` (nothing succeeded) or `PARTIAL`
  (an earlier step succeeded).

## Key safety invariants (tested)

1. A policy-rejected plan emits no `task_completed` and runs no adapter.
2. `requiresConfirmation` plans do not execute without an approval digest that
   matches the exact reviewed plan (a changed plan is rejected).
3. A failed postcondition is never reported as success.
4. Cancellation prevents any later step from starting.
5. A timed-out step is not blindly replayed; a repeated `idempotencyKey` is
   suppressed.
6. Secrets are redacted from the journal and never appear in events.
