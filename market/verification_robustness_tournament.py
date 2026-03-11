import asyncio
import logging
import os
import json
from market.runner import MarketRunner
from market.orchestrator import AgentAction
from market.core.state import AgentPortfolio, MarketAsset
from unittest.mock import AsyncMock, patch, MagicMock

async def run_verification():
    logging.basicConfig(level=logging.INFO)
    
    # 1. Setup Runner
    runner = MarketRunner("Test Robustness", n_agents=3, budget=300.0)
    runner.orchestrator.initialize = AsyncMock() # Skip real git clones
    
    # Mock agents in state
    for i in range(3):
        aid = f"agent_{i}"
        runner.orchestrator.state.agents[aid] = AgentPortfolio(agent_id=aid, wealth=100.0)
        runner.orchestrator.state.assets[f"cand_{i}"] = MarketAsset(id=f"cand_{i}", type="CANDIDATE", description=f"C{i}")

    # 2. Setup Sharks with different failure modes
    # agent_0: Always succeeds
    shark_0 = AsyncMock()
    shark_0.agent_id = "agent_0"
    shark_0.get_action.return_value = AgentAction("agent_0", beliefs={"cand_0": 0.8})
    shark_0.shutdown = AsyncMock()
    
    # agent_1: Always times out (should return fallback AgentAction with error)
    shark_1 = AsyncMock()
    shark_1.agent_id = "agent_1"
    # Simulated internal fallback in Shark.get_action
    shark_1.get_action.return_value = AgentAction("agent_1", error="Request timed out", retry_count=3)
    shark_1.shutdown = AsyncMock()
    
    # agent_2: Raises unexpected exception (should be caught by MarketRunner.run_loop)
    shark_2 = AsyncMock()
    shark_2.agent_id = "agent_2"
    shark_2.get_action.side_effect = Exception("Critical bug in agent server")
    shark_2.shutdown = AsyncMock()
    
    runner.sharks = {
        "agent_0": shark_0,
        "agent_1": shark_1,
        "agent_2": shark_2
    }
    
    # 3. Run Loop
    print("\n--- Starting Robustness Verification Tournament ---")
    await runner.run_loop(max_rounds=3, stream_ui=False, json_logs=False)
    print("--- Tournament Finished Successfully ---\n")
    
    # 4. Assertions
    state = runner.orchestrator.state
    print(f"Final Round: {state.round_num}")
    
    # agent_1 should have 3 failures recorded
    print(f"Agent 1 Failure Count: {state.agents['agent_1'].failure_count}")
    print(f"Agent 1 Last Error: {state.agents['agent_1'].last_error}")
    
    # agent_2 should also have 3 failures recorded
    print(f"Agent 2 Failure Count: {state.agents['agent_2'].failure_count}")
    print(f"Agent 2 Last Error: {state.agents['agent_2'].last_error}")
    
    assert state.round_num == 3
    assert state.agents['agent_1'].failure_count == 3
    assert state.agents['agent_2'].failure_count == 3
    assert "Critical bug" in state.agents['agent_2'].last_error

if __name__ == "__main__":
    asyncio.run(run_verification())
