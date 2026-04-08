---
phase: 01-achieve-100-unit-test-coverage
plan: "01"
subsystem: test-infrastructure
tags: [pytest, coverage, conftest, mock, fixtures]
dependency_graph:
  requires: []
  provides: [mock_page fixture, install_stubs helper, pytest config, coverage config]
  affects: [all subsequent test plans in phase 01]
tech_stack:
  added: [pytest-asyncio (config), coverage.py config]
  patterns: [MockPage fixture pattern, sys.modules stub pattern]
key_files:
  created:
    - tests/conftest.py
  modified:
    - pyproject.toml
    - .github/workflows/ci.yml
    - skills/orchestrator/engine/engine_setup.py
    - skills/orchestrator/engine/platforms/inject_utils.py
    - tests/test_prompt_echo.py
decisions:
  - "_stub_engine_setup kept as plain callable (not fixture) to allow Plan 03 to swap in real module"
  - "fail_under=100 added to pyproject.toml but --cov-fail-under=100 deferred to Plan 07 in CI"
metrics:
  duration: ~10min
  completed: 2026-04-08
  tasks_completed: 2
  files_created: 1
  files_modified: 5
---

# Phase 01 Plan 01: Test Infrastructure Setup Summary

**One-liner:** Shared MockPage fixture in conftest.py, pytest-asyncio config, three-source-tree coverage config, and pragma annotations on genuinely untestable sys.exit lines.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create conftest.py with MockPage fixture and shared helpers | 9861769 | tests/conftest.py |
| 2 | Add pytest/coverage config and pragma: no cover annotations | 77972ce | pyproject.toml, ci.yml, engine_setup.py, inject_utils.py, test_prompt_echo.py |

## Decisions Made

1. `_stub_engine_setup` is a plain callable function, not a pytest fixture. This lets Plan 03's `test_engine_setup.py` pop it from `sys.modules`, import the real module, and restore the stub in teardown — a fixture with autouse would prevent this pattern.

2. `fail_under = 100` is set in `pyproject.toml` (coverage tool config) now, but `--cov-fail-under=100` is NOT yet added to CI — that flag is deferred to Plan 07 once all tests are written.

## Verification Results

- 100 tests pass (99 original + 1 new `test_is_prompt_echo_empty_sigs`)
- `pyproject.toml` has `asyncio_mode = "auto"` and `fail_under = 100`
- `prompt_echo.py` at 100% coverage (24/24 lines)
- `grep "autouse" tests/conftest.py` returns no matches
- CI yaml now covers `skills/comparator` and `skills/landscape-researcher`
- `grep "pragma: no cover" engine_setup.py` returns 3 matches

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. The conftest stubs are test infrastructure, not production stubs.

## Threat Flags

None. Test infrastructure only — no new network endpoints, auth paths, or schema changes introduced.

## Self-Check: PASSED

- tests/conftest.py: FOUND
- pyproject.toml (asyncio_mode): FOUND
- Commit 9861769: FOUND
- Commit 77972ce: FOUND
