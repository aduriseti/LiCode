# Track Specification: Robust Retries and Fallbacks (Agent Failures)

## Overview
This track addresses brittle agent execution in the Logical Induction Market. Currently, agent timeouts or connection errors can cause the entire tournament to crash. We need to implement robust retries with scaling timeouts and graceful fallbacks so the tournament can proceed even if some agents fail in a round.

## Functional Requirements

### 1. Robust Agent Connection and Inference
- **Connection Retries:** Implement a retry loop for `setup_agent` (server startup and session initialization) in `runner.py`.
- **Inference Retries:** In `Shark.get_action`, if an inference call fails (timeout or network), retry with an increased (doubled) timeout.
- **Scaling Timeouts:** Retries should use exponentially increasing timeouts (e.g., initial 120s, then 240s, then 480s, etc.), capped at `max_backoff`.
- **Constraint:** Do not increase the default `agent_timeout` in `evaluate_swe_bench.py` beyond its current setting.

### 2. Graceful Fallbacks for Failed Agents
- **No-Op Action:** If an agent fails to provide a response after all retries (e.g., 3 attempts), it should NOT crash the tournament.
- **Neutral Beliefs:** Instead, the agent should contribute an "empty action" for that round: 0.0 beliefs for all candidates and no new proposals.
- **Resilient Round Execution:** Use `asyncio.gather(..., return_exceptions=True)` in `runner.py`'s `run_loop` to ensure one agent's failure doesn't halt the round.
- **Round-by-Round Persistence:** Failing in one round should not disqualify the agent from future rounds. The system should continue trying to get an action from the failing agent in subsequent rounds.

### 3. Error Reporting and Diagnostics
- **Enhanced Logging:** Log all agent failures and retry attempts to the tournament logs.
- **Dashboard Integration:** Stream special "error" events to the dashboard when an agent fails a round or a connection attempt.
- **Market State Metadata:** Record failure counts and last error messages for each agent in the `MarketState` (to be serialized in JSON logs).

### 4. Encoding Fix for Report Generation
- **Decoding Resilience:** Fix the `UnicodeDecodeError` in `orchestrator.py`'s `get_final_report` by using `errors='replace'` when decoding `git diff` output.

## Non-Functional Requirements
- **Verification:** Every retry and fallback mechanism must be verified with unit tests.
- **Reliability:** The orchestrator must be able to complete a tournament even if N-1 agents are completely offline.

## Acceptance Criteria
- [ ] Agents that timeout in a round produce a neutral action (empty beliefs) instead of crashing.
- [ ] Agents are retried in the next round even after failing the current one.
- [ ] Initial server connections are retried at least 3 times.
- [ ] The tournament finishes successfully even if multiple agents experience connection errors.
- [ ] Final report generation succeeds even with non-UTF-8 characters in diffs.

## Out of Scope
- Modifying the agent's internal logic or prompts.
- Improving the LLM's response quality (this is about the *system's* resilience).
