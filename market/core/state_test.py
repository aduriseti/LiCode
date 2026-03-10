import unittest

from market.core.state import AgentPortfolio, MarketAsset, MarketState


class TestMarketState(unittest.TestCase):
    def test_serialization(self):
        # Create a complex state
        state = MarketState(round_num=1, liquidity_b=100.0, whale_wealth=5000.0)

        # Add asset
        asset = MarketAsset(id="test_1", type="VERIFIER", description="Checks for null")
        asset.q_yes = 10
        state.assets["test_1"] = asset

        # Add agent
        agent = AgentPortfolio(agent_id="agent_007", wealth=100.0)
        agent.shares["test_1"] = 5.0
        state.agents["agent_007"] = agent

        # Add failures
        state.test_failures["test_1:cand_2"] = True

        # Serialize
        json_str = state.to_json()

        # Deserialize
        state_loaded = MarketState.from_json(json_str)

        # Verify
        self.assertEqual(state_loaded.round_num, 1)
        self.assertEqual(state_loaded.whale_wealth, 5000.0)
        self.assertEqual(state_loaded.assets["test_1"].description, "Checks for null")
        self.assertEqual(state_loaded.agents["agent_007"].shares["test_1"], 5.0)
        self.assertTrue(state_loaded.test_failures["test_1:cand_2"])


if __name__ == "__main__":
    unittest.main()
