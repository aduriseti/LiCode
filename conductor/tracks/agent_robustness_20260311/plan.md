# Implementation Plan: Robust Agent Retries and Fallbacks

## Phase 1: Robust Agent Inference and Fallbacks
Task: Update `market/agents/shark.py` to handle inference timeouts and provide empty actions.
- [ ] Task: Write unit tests for `Shark.get_action` fallback behavior (TDD).
- [ ] Task: Update `Shark.get_action` to return an empty `AgentAction` on exhausted retries instead of raising `FatalAgentError`.
- [ ] Task: Ensure `current_timeout` in the retry loop doubles on each attempt and is capped at `max_backoff`.
- [ ] Task: Verify unit tests pass.

## Phase 2: Resilient Tournament Execution
Task: Update `market/runner.py` to handle agent initialization and round failures.
- [ ] Task: Write unit tests for `MarketRunner.run_loop` with failing agents (TDD).
- [ ] Task: Update `MarketRunner.run_loop` to use `asyncio.gather(..., return_exceptions=True)`.
- [ ] Task: Process results from `gather` and log/report failures without crashing.
- [ ] Task: Implement a retry loop for `setup_agent` (at least 3 attempts) during `initialize`.
- [ ] Task: Update `setup_agent` to return `None` (or similar) on failure and filter the `sharks` dict.
- [ ] Task: Verify unit tests pass.

## Phase 3: Reporting and Diagnostics
Task: Enhance logging and dashboard reporting for failures.
- [ ] Task: Add `failure_count` and `last_error` to the agent state in `MarketState` (`market/core/state.py`).
- [ ] Task: Stream failure events to the dashboard from `Shark` or `MarketRunner`.
- [ ] Task: Update `Orchestrator.get_final_report` with the UTF-8 encoding fix (`errors='replace'`).
- [ ] Task: Verify report generation with a mock non-UTF-8 diff.

## Phase 4: Final Verification
- [ ] Task: Run a multi-round tournament with simulated agent timeouts and verify it completes.
- [ ] Task: Conductor - User Manual Verification 'Robustness' (Protocol in workflow.md).
