# Person 1 - Desktop Runtime & Safety

This workstream owns the ATLAS execution runtime: the part of the local Python
backend (`services/atlas-core`) that safely performs desktop actions after the
policy engine authorizes them.

## What lives where

Production code (canonical location, `services/atlas-core/src/atlas/`):

| Module | Responsibility |
|---|---|
| `policy/` | Authorization boundary: schema validation, action allowlist, risk-tier floor, argument validation, confirmation decision, stable plan digest. |
| `adapters/` | `ActionAdapter` protocol + `FakeActionAdapter` (mock, no OS actions) + `WindowsActionAdapter` (real `app.open` via resolved executable + psutil verification). Failure taxonomy. |
| `verifier/` | Pre/postcondition checks from real observations (fail-closed on unknown condition types). |
| `journal/` | Append-only execution ledger with secret redaction (JSONL + in-memory). |
| `executor/` | The one canonical path: policy -> confirmation -> per-step execute (timeout+cancel) -> verify -> contract events. `build_runtime` assembly + `demo` CLI. |

Tests: `services/atlas-core/tests/runtime/`.

Workstream notes/design (this folder): `design/`, `docs/`, this README, and
`acceptance-checklist.md`.

## Run it

From `services/atlas-core` (Windows, Python 3.11+, `pip install jsonschema psutil pytest`):

```powershell
# Unit + contract + failure-injection tests (safe, no real actions)
$env:PYTHONPATH="src"; python -m pytest tests/runtime -v

# Opt-in live Windows smoke test (really opens & closes notepad)
$env:ATLAS_RUN_LIVE_TESTS="1"; python -m pytest tests/runtime/test_windows_live.py -v

# Terminal demo of the three required paths
$env:PYTHONPATH="src"
python -m atlas.executor.demo --plan ../../packages/contracts/examples/plan.valid.json --allowed-apps notepad,calc --yes          # success (verified)
python -m atlas.executor.demo --plan ../../packages/contracts/examples/plan.invalid-unknown-action.json --yes                      # blocked (shell.exec)
python -m atlas.executor.demo --plan ../../packages/contracts/examples/plan.valid.json --allowed-apps notepad,calc --yes --live    # real app.open
```

## Integration

The orchestrator and Person 4 consume `atlas.executor.build_runtime(...)` and
`runtime.run(plan, approved_digest=..., is_cancelled=...)`. See
[`design/runtime-interface.md`](design/runtime-interface.md) and
[`design/failure-taxonomy.md`](design/failure-taxonomy.md).

## Boundaries honoured

Only files under the Person 1 paths (INSTRUCTIONS section 1) were created or
modified. No shared contracts, root config, scripts, or other personas'
modules were touched. The runtime consumes `packages/contracts/` read-only.
