# Acceptance checklist - Person 1 - Runtime (Common PRD section 10)

- [x] Only registered actions can execute. (`test_policy.py::test_valid_plan_is_allowed`, `test_unknown_action_is_rejected`)
- [x] Unsupported paths/apps/actions are rejected. (`test_app_not_in_allowlist_is_rejected`, `test_rejected_plan_never_executes`, blocked-action rejection)
- [x] Preconditions and postconditions are checked. (`verifier/checks.py`; `test_postcondition_failure_is_not_success`)
- [x] Failure does not become a success message. (`test_postcondition_failure_is_not_success`, `test_launch_failure_is_reported_as_failure`)
- [x] Cancellation prevents future steps. (`test_cancellation_prevents_future_steps`)
- [x] Tests cover timeout, missing target, stale selector, and duplicate request. (`test_timeout_is_reported`, `test_missing_target_appid`, `test_stale_selector_window_vanishes`, `test_duplicate_idempotency_key_is_suppressed`)

## Additional verified safety properties

- [x] Risk tiers cannot be lowered by plan/model output. (`test_lowered_risk_tier_is_rejected`)
- [x] Confirmation binds to the exact reviewed plan digest; a changed plan is rejected. (`test_confirmation_and_journal.py`)
- [x] Every emitted event validates against `events.schema.json`. (`test_event_contract.py`)
- [x] Secrets are redacted from the journal and never appear in events. (`test_journal_redacts_secrets`, `test_journal_entries_have_no_raw_secrets`)
- [x] A real Windows `app.open` launches and is verified via process scan, then cleaned up. (`test_windows_live.py`, opt-in)

## Test run evidence

`python -m pytest tests/runtime -v` from `services/atlas-core`:
- 23 passed by default; 24 passed with `ATLAS_RUN_LIVE_TESTS=1` on Windows
  (adds the live notepad smoke test). See `../docs/COMPLETION-REPORT.md`.
