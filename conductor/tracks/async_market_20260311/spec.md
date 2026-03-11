# Specification: Asynchronous Event-Driven Market Execution

## Overview
This track converts the LiCode market from a synchronous, global-batch process to an asynchronous, event-driven model. Instead of waiting for all agents to finish their turns before clearing the market, the system will process actions in smaller batches of at least 2 agents as they become available. This rewards faster agents with a first-mover advantage and increases market velocity.

## Functional Requirements
- **Async Runner Loop:**
  - Replace `asyncio.gather` with a dynamic task pool that waits for the first available agent responses.
  - Implement a `2-agent` threshold for market ticks: the `process_round` will be called as soon as at least 2 agents have submitted their actions.
  - If the number of alive agents drops to 1, the remaining agent is allowed to complete their action, and the tournament terminates after that round (assuming not bankrupt).
- **Asynchronous Economic Model:**
  - **Inference Tax:** Tax should only be deducted from the agents who actually submitted an action in a given tick (Per-Action Tax).
  - **Bond Maturation:** Bonds should mature based on the number of market events (async rounds) rather than global cycles. Default: `lock_period = N_agents` events.
- **Oracle Optimization:**
  - The Oracle (test runner) should only execute if a new verifier was proposed or code was updated in the current batch of actions (On-Demand execution).
- **Concurrency Control:**
  - Handle task cancellation for agents that go bankrupt during a round.
  - Ensure async-safe state updates for the shared market state.

## Non-Functional Requirements
- **First-Mover Advantage:** Faster agents should be able to move the market price before slower agents complete their turns.
- **Latency Handling:** Agents must be able to handle "slippage" if the market price moves while they are thinking.

## Acceptance Criteria
- [ ] Market clears individually as soon as 2 agent actions are buffered.
- [ ] Slow agents are NOT drained of wealth by taxes while they are still processing a turn.
- [ ] Oracle execution frequency is reduced for rounds containing only bets.
- [ ] Tournament correctly handles 1-agent scenarios and terminates appropriately.
- [ ] `docs/design.md` is updated to reflect the new async model.

## Out of Scope
- Implementing advanced slippage protection.
- Multi-agent parallel code updates (sequential application within the batch is acceptable).
