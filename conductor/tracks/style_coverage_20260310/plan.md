# Implementation Plan: coding style & test coverage

## Phase 1: Tooling Configuration [checkpoint: 82e1ac9]
- [x] **Task: Configure Python linting and formatting (Ruff)** ae5f1b9
    - [ ] Install `ruff` if not present.
    - [ ] Create or update `pyproject.toml` or `ruff.toml` with project-specific rules.
    - [ ] Verify `ruff` runs correctly.
- [x] **Task: Configure TypeScript linting and formatting (ESLint/Prettier)** 1d598ac
    - [ ] Install `eslint` and `prettier` dependencies in `.opencode/`.
    - [ ] Create or update `.eslintrc.json` and `.prettierrc`.
    - [ ] Verify `eslint` and `prettier` run correctly.
- [x] **Task: Configure coverage reporting for Pytest and Vitest** f6e7c4d
    - [ ] Install `pytest-cov` and configure it.
    - [ ] Update `vitest.config.ts` to include coverage reporting using `v8`.
- [x] **Task: Conductor - User Manual Verification 'Phase 1: Tooling Configuration' (Protocol in workflow.md)** 82e1ac9

## Phase 2: Linting & Formatting Alignment
- [ ] **Task: Apply Ruff auto-fixes and manual corrections to Python codebase**
    - [ ] Run `ruff check --fix` on `market/`.
    - [ ] Manually fix any remaining errors.
    - [ ] Run `ruff format` on `market/`.
- [ ] **Task: Apply Prettier and ESLint fixes to TypeScript codebase**
    - [ ] Run `npx prettier --write .` in `.opencode/`.
    - [ ] Run `npx eslint --fix .` in `.opencode/`.
    - [ ] Manually fix any remaining errors.
- [ ] **Task: Conductor - User Manual Verification 'Phase 2: Linting & Formatting Alignment' (Protocol in workflow.md)**

## Phase 3: Coverage Expansion (Python)
- [ ] **Task: Identify low-coverage areas in `market/` core logic**
    - [ ] Run initial coverage report for `market/`.
    - [ ] Document modules with coverage <80%.
- [ ] **Task: Write tests for `market/core/lmsr.py`**
    - [ ] Implement TDD: Write failing tests for key LMSR functions (cost, price, wagers).
    - [ ] Ensure all LMSR edge cases (high confidence, low budget) are covered.
- [ ] **Task: Write tests for `market/orchestrator.py`**
    - [ ] Implement TDD: Write failing tests for round processing and state transitions.
    - [ ] Verify correct wealth conservation.
- [ ] **Task: Write tests for `market/runner.py`**
    - [ ] Implement TDD: Write failing tests for agent initialization and dashboard integration.
    - [ ] Verify correct server process management.
- [ ] **Task: Conductor - User Manual Verification 'Phase 3: Coverage Expansion (Python)' (Protocol in workflow.md)**

## Phase 4: Coverage Expansion (TypeScript)
- [ ] **Task: Identify low-coverage areas in `.opencode/lib/`**
    - [ ] Run initial coverage report for TypeScript code.
    - [ ] Document modules with coverage <80%.
- [ ] **Task: Write tests for `dashboard-server.ts` and `dashboard.app.ts`**
    - [ ] Implement TDD: Write failing tests for API endpoints and Socket.IO events.
    - [ ] Verify correct server startup and shutdown.
- [ ] **Task: Write tests for `terminal.manager.ts`**
    - [ ] Implement TDD: Write failing tests for agent registration and PTY management.
    - [ ] Verify correct WebSocket proxying.
- [ ] **Task: Conductor - User Manual Verification 'Phase 4: Coverage Expansion (TypeScript)' (Protocol in workflow.md)**

## Phase 5: Finalization
- [ ] **Task: Final verification of all quality gates**
    - [ ] Ensure >80% coverage across all modules.
    - [ ] Ensure no linting errors remain.
    - [ ] All tests passing in CI mode.
- [ ] **Task: Conductor - User Manual Verification 'Phase 5: Finalization' (Protocol in workflow.md)**
