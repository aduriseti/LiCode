# Specification: coding style & test coverage

## Goal
Establish a robust quality baseline for the LiCode project by enforcing consistent coding styles and achieving high test coverage (>80%) across both Python and TypeScript components.

## Success Criteria
1.  **Python Codebase:**
    -   Successfully configured `ruff` for linting and formatting.
    -   Existing code in `market/` passes all `ruff` checks and follows the `ruff format` style.
    -   `pytest` coverage for `market/` reaches >80%.
2.  **TypeScript Codebase:**
    -   Successfully configured `eslint` and `prettier`.
    -   Existing code in `.opencode/lib/` passes all `eslint` checks and follows the `prettier` style.
    -   `vitest` coverage for `.opencode/lib/` reaches >80%.
3.  **CI Readiness:**
    -   All linting and test commands are non-interactive and suitable for CI environments.
    -   Automated coverage reports are generated.

## Technical Requirements
-   **Python Tools:** `ruff`, `pytest`, `pytest-cov`.
-   **TypeScript Tools:** `eslint`, `prettier`, `vitest`.
-   **Coverage Targets:** Global project-wide and module-specific coverage >80%.
