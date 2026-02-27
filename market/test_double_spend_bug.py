import unittest
from unittest import mock
import os
import shutil
import tempfile
import asyncio
from market.orchestrator import Orchestrator, AgentAction
from market.core.state import MarketState, MarketAsset

class TestDoubleSpendBug(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        
    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir)

    async def test_double_spend_on_verifier_and_beliefs(self):
        """
        Replicates the bug from the logs where an agent proposes a verifier (buying a bond)
        and submits beliefs in the same round, causing them to double-spend their frozen wealth
        and end up with negative wealth.
        """
        orch = Orchestrator("Double Spend Test", n_agents=3, budget=1000.0, base_dir=self.test_dir)
        await orch.initialize()
        
        # Each agent starts with 333.33 wealth
        agent_id = "agent_0"
        initial_wealth = orch.state.agents[agent_id].wealth
        self.assertAlmostEqual(initial_wealth, 333.33, places=2)
        
        # Create distinct dummy verifier paths to propose for each agent
        for i in range(3):
            cand_dir = os.path.join(self.test_dir, "worktrees", f"cand_{i}")
            v_src = os.path.join(cand_dir, "v_test")
            os.makedirs(v_src, exist_ok=True)
            with open(os.path.join(v_src, "run.sh"), "w") as f:
                # Different contents so they get different hashes
                f.write(f"#!/bin/bash\necho 'Agent {i}'")
            
        # Agent 0 proposes the verifier AND places bets
        action0 = AgentAction(
            agent_id="agent_0",
            beliefs={"cand_0": 0.6, "cand_1": 0.2, "cand_2": 0.2},
            proposals=[{"type": "VERIFIER", "path": "v_test"}]
        )
        
        # Agent 1 proposes the verifier AND places bets
        action1 = AgentAction(
            agent_id="agent_1",
            beliefs={"cand_0": 0.05, "cand_1": 0.9, "cand_2": 0.05},
            proposals=[{"type": "VERIFIER", "path": "v_test"}]
        )
        
        # Agent 2 proposes the verifier AND places bets
        action2 = AgentAction(
            agent_id="agent_2",
            beliefs={"cand_2": 0.9, "cand_0": 0.05, "cand_1": 0.05},
            proposals=[{"type": "VERIFIER", "path": "v_test"}]
        )
        
        # Mock the oracle to inject the specific test failures from the logs
        async def mock_run_oracle():
            # Find the generated verifier IDs by looking at the assets
            vids = [aid for aid, a in orch.state.assets.items() if a.type == "VERIFIER"]
            # We expect 3 verifiers, let's map them arbitrarily to the failure pattern
            v_0 = vids[0] if len(vids) > 0 else "v_0"
            v_1 = vids[1] if len(vids) > 1 else "v_1"
            v_2 = vids[2] if len(vids) > 2 else "v_2"
            
            # Agent 0's verifier fails on cand_2 and cand_1
            orch.state.test_failures[f"{v_0}:cand_2"] = True
            orch.state.test_failures[f"{v_0}:cand_1"] = True
            
            # Agent 1's verifier fails on cand_2 and cand_0
            orch.state.test_failures[f"{v_1}:cand_2"] = True
            orch.state.test_failures[f"{v_1}:cand_0"] = True
            
            # Agent 2's verifier fails on cand_0 and cand_1
            orch.state.test_failures[f"{v_2}:cand_0"] = True
            orch.state.test_failures[f"{v_2}:cand_1"] = True

        with mock.patch.object(orch, '_run_oracle', side_effect=mock_run_oracle):
            await orch.process_round([action0, action1, action2])
            
        final_liquid_wealth = orch.state.agents[agent_id].wealth
        bond_value = sum(b.q_shares * orch.state.get_asset_price(b.asset_id) 
                         for b in orch.state.bonds if b.agent_id == agent_id)
                         
        total_value = final_liquid_wealth + bond_value
        
        # The agent should not be bankrupt, and its wealth should not be drastically negative
        self.assertGreaterEqual(final_liquid_wealth, 0, "Agent's liquid wealth went negative due to double spend!")

if __name__ == "__main__":
    unittest.main()