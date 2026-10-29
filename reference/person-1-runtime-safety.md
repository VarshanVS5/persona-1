# Person 1 (Desktop Runtime & Safety) - deliverable pointer

The latest task prompt named `...\SVVAM-main\reference` as the deliverable
location. That folder is **not** part of the ATLAS canonical repository
structure (Common PRD section 3), and the frozen architecture requires the
runtime production code to live at its canonical path so it integrates as one
backend. Placing it elsewhere would create a duplicate module, which the PRD
explicitly forbids. So the actual deliverable is in the owned canonical paths,
and this file just points to it.

## Where the work actually is

Production runtime (`services/atlas-core/src/atlas/`):
- `policy/` - authorization boundary (schema, allowlist, risk-tier floor, args, digest)
- `adapters/` - fake (mock) + real Windows `app.open` adapter + failure taxonomy
- `verifier/` - pre/postcondition checks from real observations
- `journal/` - append-only ledger with secret redaction
- `executor/` - canonical execute path, events, timeout/cancel, `build_runtime`, `demo`

Tests: `services/atlas-core/tests/runtime/` (24 tests, all passing).

Workstream notes & reports: `workstreams/person-1-runtime-safety/`
- `README.md` - how to run
- `acceptance-checklist.md` - checklist with test evidence
- `design/runtime-interface.md` - the stable integration interface
- `design/failure-taxonomy.md` - failure codes and safety invariants
- `docs/COMPLETION-REPORT.md` - full completion report

## Quick start

From `services/atlas-core` (Windows, Python 3.11+):

```powershell
$env:PYTHONPATH="src"; python -m pytest tests/runtime -v
$env:PYTHONPATH="src"; python -m atlas.executor.demo --plan ../../packages/contracts/examples/plan.valid.json --allowed-apps notepad,calc --yes --live
```
