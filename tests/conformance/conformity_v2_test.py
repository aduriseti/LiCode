import unittest

from market.core.state import AgentPortfolio, MarketAsset
from market.orchestrator import Orchestrator


class TestDesignConformityV2(unittest.IsolatedAsyncioTestCase):
    async def test_whale_lag_with_two_agents(self):
        orch = Orchestrator("Test", n_agents=2, budget=1000.0)
        await orch.initialize()

        # Baseline price ~0.5
        p0 = orch.state.get_asset_price("cand_0")

        # 1. Mock Oracle failure for cand_0 in THIS round
        async def mock_run_oracle():
            orch.state.assets["v_test"] = MarketAsset(
                id="v_test", type="VERIFIER", description="Test", q_yes=100.0
            )  # High validity
            orch.state.test_failures["v_test:cand_0"] = True

        orch._run_oracle = mock_run_oracle

        await orch.process_round([])

        p1 = orch.state.get_asset_price("cand_0")
        print(f"Price before: {p0:.4f}, Price after: {p1:.4f}")
        self.assertLess(p1, p0, "Whale did not react to failure in the same round")

    async def test_pool_sync_qmatch(self):
        """Design 4.D.258: Pool should reflect matched shares."""
        orch = Orchestrator("Test", n_agents=2, budget=1000.0)
        # Mock agents
        orch.state.agents["agent_0"] = AgentPortfolio(agent_id="agent_0", wealth=500.0)
        orch.state.agents["agent_1"] = AgentPortfolio(agent_id="agent_1", wealth=500.0)
        orch.state.assets["cand_0"] = MarketAsset(id="cand_0", type="CANDIDATE", description="Test")

        # Opposing wagers
        # At P=0.5, 100 credits buys 200 shares.
        intents = [("agent_0", "cand_0", 100.0), ("agent_1", "cand_0", -100.0)]
        orch._execute_wager_batch(intents)

        asset = orch.state.assets["cand_0"]
        # Design 4.H.6 Refinement (Net Form): Perfectly matched wagers should result in 0.0 pool depth displacement.
        self.assertAlmostEqual(asset.q_yes, 0.0, places=5)
        self.assertAlmostEqual(asset.q_no, 0.0, places=5)

    async def test_maturation_order(self):
        """Design 4.H.10: Bond maturation happens after trades."""
        # This is harder to test without instrumenting process_round
        pass


if __name__ == "__main__":
    unittest.main()
