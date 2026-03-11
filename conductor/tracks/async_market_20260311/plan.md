# Implementation Plan: Asynchronous Event-Driven Market Execution

This plan outlines the conversion of the LiCode market execution from synchronous global batching to an asynchronous, event-driven model with a 2-agent batching threshold.

## Phase 1: Research & Baseline Verification
- [ ] Task: Research current `MarketRunner.run_loop` and `Orchestrator.process_round` implementation.
- [ ] Task: Verify existing test suite passes (`pytest market/runner_test.py`).
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Research & Baseline Verification' (Protocol in workflow.md)

## Phase 2: Asynchronous Runner Loop
- [ ] Task: Write failing test for asynchronous market tick (e.g., fast agent gets turn processed while slow agent is thinking).
- [ ] Task: Implement `action_buffer` and `pending_tasks` pool in `MarketRunner.run_loop`.
- [ ] Task: Implement "at least 2 agents" (or final agent) batching logic in `MarketRunner`.
- [ ] Task: Verify that `process_round` is called correctly with smaller batches.
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Asynchronous Runner Loop' (Protocol in workflow.md)

## Phase 3: Per-Action Economic Model & Oracle Optimization
- [ ] Task: Write failing test for "Tax Trap" (slow agent taxed during other agents' ticks).
- [ ] Task: Modify `Orchestrator.process_round` to only deduct tax from active participants in the batch.
- [ ] Task: Write failing test for redundant Oracle execution.
- [ ] Task: Implement optimized Oracle execution (skip if no new verifiers/code updates).
- [ ] Task: Update bond maturation to use event-based `lock_period`.
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Per-Action Economic Model & Oracle Optimization' (Protocol in workflow.md)

## Phase 4: Refinement & Documentation
- [ ] Task: Update `docs/design.md` with the new asynchronous execution flow.
- [ ] Task: Perform final integration test with multiple agents of varying speeds.
- [ ] Task: Conductor - User Manual Verification 'Phase 4: Refinement & Documentation' (Protocol in workflow.md)
