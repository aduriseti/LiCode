import unittest

from market.core.state import MarketAsset
from market.orchestrator import AgentAction, Orchestrator


class TestWealthConservation(unittest.IsolatedAsyncioTestCase):
    async def test_zero_sum_conservation_extended(self):
        """
        Verify that total wealth is conserved across multiple rounds
        with complex trading patterns, bond creation, and whale intervention.
        """
        initial_budget = 3000.0
        n_agents = 3
        # Whale = 3000, Agents = 3*1000. Total = 6000.
        orch = Orchestrator("Conservation Test", n_agents=n_agents, budget=initial_budget)
        await orch.initialize()

        orch.inference_tax = 0.0  # Strict zero-sum

        def get_total_wealth():
            w = orch.state.whale_wealth
            for agent in orch.state.agents.values():
                w += agent.wealth
            return w

        start_wealth = get_total_wealth()
        expected_total = 6000.0
        self.assertAlmostEqual(start_wealth, expected_total)

        # --- Round 1: Aggressive Trading ---
        actions_r1 = [
            AgentAction("agent_0", beliefs={"cand_0": 0.9}),
            AgentAction("agent_1", beliefs={"cand_0": 0.1}),
            AgentAction("agent_2", beliefs={"cand_1": 0.8}),
        ]
        await orch.process_round(actions_r1)
        self.assertAlmostEqual(get_total_wealth(), expected_total, places=5, msg="Leaked in R1")

        # --- Round 2: Whale Intervention ---
        # Simulate a test failure that triggers Whale shorting
        orch.state.test_failures["v_manual:cand_0"] = True
        # Manually add a verifier to trigger Whale logic
        orch.state.assets["v_manual"] = MarketAsset(
            id="v_manual", type="VERIFIER", description="Manual", q_yes=10.0
        )

        actions_r2 = [
            AgentAction("agent_0", beliefs={"cand_0": 0.5}),  # Agent 0 changes mind
        ]
        await orch.process_round(actions_r2)
        self.assertAlmostEqual(
            get_total_wealth(), expected_total, places=5, msg="Leaked in R2 (Whale Intervene)"
        )

        # --- Round 3: Bond Creation & Maturation ---
        # 1. Setup a Verifier source in agent_0's worktree
        import os

        cand_dir = os.path.join(orch.base_dir, "worktrees", "cand_0")
        v_src = os.path.join(cand_dir, "v_bond")
        os.makedirs(v_src, exist_ok=True)
        with open(os.path.join(v_src, "run.sh"), "w") as f:
            f.write("#!/bin/bash\nexit 0")

        actions_r3 = [AgentAction("agent_0", proposals=[{"type": "VERIFIER", "path": "v_bond"}])]
        # Increase lock period slightly to ensure maturation happens across rounds
        orch.bond_lock_period = 1

        await orch.process_round(actions_r3)
        self.assertAlmostEqual(
            get_total_wealth(), expected_total, places=5, msg="Leaked in R3 (Bond Create)"
        )

        # Round 4: Bond Maturation
        await orch.process_round([])
        self.assertAlmostEqual(
            get_total_wealth(), expected_total, places=5, msg="Leaked in R4 (Bond Mature)"
        )

        # --- Final Sanity ---
        self.assertAlmostEqual(get_total_wealth(), expected_total, places=5)
        # All non-bond shares should be gone
        for agent in orch.state.agents.values():
            # Only count shares that ARENT in a bond
            bond_assets = [b.asset_id for b in orch.state.bonds if b.agent_id == agent.agent_id]
            for aid in agent.shares:
                if aid not in bond_assets:
                    self.assertAlmostEqual(agent.shares[aid], 0.0, places=4)


if __name__ == "__main__":
    unittest.main()
