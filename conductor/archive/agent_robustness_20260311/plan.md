# Implementation Plan: Robust Agent Retries and Fallbacks

## Phase 1: Robust Agent Inference and Fallbacks [checkpoint: 237148d]
Task: Update `market/agents/shark.py` to handle inference timeouts and provide empty actions.
- [x] Task: Write unit tests for `Shark.get_action` fallback behavior (TDD). [237148d]
- [x] Task: Update `Shark.get_action` to return an empty `AgentAction` on exhausted retries instead of raising `FatalAgentError`. [237148d]
- [x] Task: Ensure `current_timeout` in the retry loop doubles on each attempt and is capped at `max_backoff`. [237148d]
- [x] Task: Verify unit tests pass. [237148d]

## Phase 2: Resilient Tournament Execution [checkpoint: 237148d]
Task: Update `market/runner.py` to handle agent initialization and round failures.
- [x] Task: Write unit tests for `MarketRunner.run_loop` with failing agents (TDD). [237148d]
- [x] Task: Update `MarketRunner.run_loop` to use `asyncio.gather(..., return_exceptions=True)`. [237148d]
- [x] Task: Process results from `gather` and log/report failures without crashing. [237148d]
- [x] Task: Implement a retry loop for `setup_agent` (at least 3 attempts) during `initialize`. [237148d]
- [x] Task: Update `setup_agent` to return `None` (or similar) on failure and filter the `sharks` dict. [237148d]
- [x] Task: Verify unit tests pass. [237148d]

## Phase 3: Reporting and Diagnostics [checkpoint: 237148d]
Task: Enhance logging and dashboard reporting for failures.
- [x] Task: Add `failure_count` and `last_error` to the agent state in `MarketState` (`market/core/state.py`). [237148d]
- [x] Task: Stream failure events to the dashboard from `Shark` or `MarketRunner`. [237148d]
- [x] Task: Update `Orchestrator.get_final_report` with the UTF-8 encoding fix (`errors='replace'`). [237148d]
- [x] Task: Verify report generation with a mock non-UTF-8 diff. [237148d]

## Phase 4: Final Verification [checkpoint: 237148d]
- [x] Task: Run a multi-round tournament with simulated agent timeouts and verify it completes. [237148d]
- [x] Task: Conductor - User Manual Verification 'Robustness' (Protocol in workflow.md). [237148d]
