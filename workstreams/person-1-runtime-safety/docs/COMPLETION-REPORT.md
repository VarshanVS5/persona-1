# Person 1 - Completion Report (Desktop Runtime & Safety)

Date: 2026-10-29. Scope: the ATLAS execution runtime and safety layer for the
Windows desktop app, built against the frozen shared contracts.

## 1. Files created / modified

All within Person 1 owned paths (INSTRUCTIONS section 1). No other-owner files touched.

Production (`services/atlas-core/src/atlas/`):
- `policy/__init__.py` (exports), `policy/types.py`, `policy/contracts.py`, `policy/engine.py`
- `adapters/__init__.py` (exports), `adapters/base.py`, `adapters/fake.py`, `adapters/windows.py`
- `verifier/__init__.py` (exports), `verifier/checks.py`
- `journal/__init__.py` (exports), `journal/ledger.py`
- `executor/__init__.py` (exports), `executor/events.py`, `executor/runtime.py`, `executor/factory.py`, `executor/demo.py`

Tests (`services/atlas-core/tests/runtime/`):
- `conftest.py`, `test_policy.py`, `test_runtime.py`, `test_confirmation_and_journal.py`,
  `test_event_contract.py`, `test_windows_live.py`

Workstream docs (`workstreams/person-1-runtime-safety/`):
- `README.md`, `acceptance-checklist.md` (updated), `design/failure-taxonomy.md`,
  `design/runtime-interface.md`, `docs/COMPLETION-REPORT.md` (this file)

The `__init__.py` files already existed as owner-stamped placeholders inside my
owned modules; I extended them with exports, preserving the OWNER header.

## 2. Features actually implemented

- **Policy engine (authorization boundary).** JSON-Schema validation against
  `task-plan.schema.json`; allowlist from `action-registry.json` (only
  registered actions run); blocked-category rejection (shell.exec, credential
  entry, etc.); risk-tier floor (a plan cannot declare a tier below the
  registry); per-action argument validation; app allowlist (`ATLAS_ALLOWED_APPS`);
  stable SHA-256 plan digest.
- **Adapters.** Protocol + failure taxonomy; `FakeActionAdapter` (deterministic
  mock, no OS actions, scriptable for timeout/stale/launch-fail); real
  `WindowsActionAdapter` that resolves an allowlisted `appId` to a known
  executable (never an arbitrary path, no `shell=True`), launches it, and
  verifies the process via `psutil`.
- **Verifier.** Pre/postcondition evaluation from real observations;
  `app.allowlisted` and `window.exists`; fail-closed on unknown condition types.
- **Journal.** Append-only ledger, in-memory + optional JSONL, recursive secret
  redaction (keys and value patterns: bearer tokens, AWS keys, `sk-` keys, long
  hex blobs).
- **Executor.** One canonical path: policy -> confirmation (digest-bound) ->
  per-step execute with per-step timeout and cooperative cancellation ->
  pre/postcondition verification -> contract-shaped events -> honest terminal
  status (SUCCEEDED/FAILED/PARTIAL/CANCELLED). Idempotency-key duplicate
  suppression; no blind retry after timeout.
- **Demo CLI + assembly factory** for direct, UI-less demonstration and for the
  orchestrator to wire in.

## 3. Integration with the Windows desktop app

The desktop UI (Tauri 2 + React, Person 3) talks to the local backend on
`127.0.0.1:8765`. The orchestrator (project owner) calls
`atlas.executor.build_runtime(...)` and `runtime.run(...)`, forwarding the
emitted `AtlasEvent`s over SSE to the UI and mapping `TaskOutcome` to
`GET /tasks/{id}`. Cancellation wires `POST /cancel` to the `is_cancelled`
callback; confirmation wires `POST /confirm`'s `planDigest` to `approved_digest`.
Full mapping in `design/runtime-interface.md`. The runtime is transport-agnostic
and owns no HTTP/registry code.

## 4. Commands used (build / run / test)

From `services/atlas-core` on Windows:
- Deps (already present on this machine): `pip install jsonschema psutil pytest`
- Tests: `$env:PYTHONPATH="src"; python -m pytest tests/runtime -v`
- Live Windows test: `$env:ATLAS_RUN_LIVE_TESTS="1"; python -m pytest tests/runtime/test_windows_live.py -v`
- Demo: `$env:PYTHONPATH="src"; python -m atlas.executor.demo --plan <plan.json> [--live] [--yes] [--allowed-apps notepad,calc]`

## 5. Tests executed - real results

- `python -m pytest tests/runtime` -> **23 passed** (default; live test skipped).
- With `ATLAS_RUN_LIVE_TESTS=1` on this Windows 11 machine -> **24 passed**
  (the live test really launched `notepad.exe`, verified it via psutil, and
  terminated it).
- Demo verified live: valid plan -> `SUCCEEDED` with `launched 'notepad'
  (notepad.exe)`; blocked `shell.exec` -> `FAILED`/rejected; lowered-risk tier
  -> `FAILED`/rejected.

## 6. Configuration / credentials still required

- `ATLAS_ALLOWED_APPS` (comma list, e.g. `notepad,calc`) supplied by the project
  owner's config/orchestrator. The runtime falls back to reading it from the
  environment until `atlas.config` is implemented.
- No LLM/AWS credentials are needed by the runtime (it never calls providers).
  Live desktop actions require a real Windows session.

## 7. Mocked / incomplete / unverified

- **Window verification is process-level**, not semantic UI-Automation.
  `window.exists` is confirmed by a `psutil` process scan. Full UIA control
  verification (uiautomation/pywinauto) is a documented follow-up, not claimed.
- **Action set is deliberately tiny**: only `app.open` (the sole registered
  action). No file, text-entry, or multi-step real actions yet. Compensation
  records are recorded by the fake adapter as a placeholder; no real rollback is
  claimed for any action.
- `FakeActionAdapter` is a clearly-labelled mock; mock mode performs no OS action.
- The event-contract test uses `jsonschema.RefResolver` (deprecation warning
  only; functionally correct).

## 8. Integration dependencies / blockers

- Consumes `packages/contracts/` (owner) read-only; consumes `TaskPlan` dicts
  from Person 2's planner (using the contract examples until that interface
  lands - no wait required).
- The repo copy on this machine is **not a git working tree** (no `.git`), so
  the branch/PR/`check-ownership.ps1` workflow in INSTRUCTIONS could not be
  exercised here. All edits were nonetheless confined to Person 1 paths.
- Owner-side wiring of `build_runtime` into `orchestrator/` + `api/` is a PR
  request (I do not edit those files).
- Backend packaging (`pyproject.toml`) is an owner placeholder, so tests use a
  local `tests/runtime/conftest.py` to put `src/` on the path.

## 9. Next highest-priority action

Request (by PR to the project owner) that `orchestrator/` call
`build_runtime(...)` / `runtime.run(...)` and relay events over SSE, so the
end-to-end UI -> planner -> policy -> execute -> verify slice runs in the actual
Tauri desktop app. Second: add one more low-risk registered action
(`app.open` of a second allowlisted app) only after the orchestrator wiring is
verified.
