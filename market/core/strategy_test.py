import unittest
from market.core.strategy import Strategy
from market.core.state import MarketState, MarketAsset

class StrategyTest(unittest.TestCase):
    
    def test_beliefs_to_wagers(self):
        state = MarketState(round_num=1, liquidity_b=100.0)
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc")
        
        # Belief 0.8 > Price 0.5 -> Buy YES
        beliefs = {"cand_0": 0.8}
        wealth = 100.0
        
        wagers = Strategy.beliefs_to_wagers(beliefs, wealth, state)
        
        self.assertEqual(len(wagers), 1)
        asset_id, wager = wagers[0]
        self.assertEqual(asset_id, "cand_0")
        self.assertTrue(wager > 0) # Positive wager (Buying YES)

    def test_no_overspend(self):
        """Verify that total absolute wagers never exceed the agent's wealth."""
        state = MarketState(round_num=1, liquidity_b=100.0)
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc")
        state.assets["cand_1"] = MarketAsset("cand_1", "CANDIDATE", "Desc")
        state.assets["cand_2"] = MarketAsset("cand_2", "CANDIDATE", "Desc")
        
        # Extreme beliefs on multiple assets will try to wager more than wealth
        beliefs = {
            "cand_0": 0.99, # Strong YES
            "cand_1": 0.01, # Strong NO
            "cand_2": 0.99  # Strong YES
        }
        wealth = 100.0
        
        wagers = Strategy.beliefs_to_wagers(beliefs, wealth, state)
        
        total_spend = sum(abs(wager) for _, wager in wagers)
        
        # Due to scaling/normalization, the total spend should be exactly the wealth (or slightly less due to floating point)
        self.assertLessEqual(total_spend, wealth + 1e-5)
        self.assertGreater(total_spend, 0)

    def test_shorting_wagers(self):
        state = MarketState(round_num=1, liquidity_b=100.0)
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc")
        
        # Belief 0.2 < Price 0.5 -> Buy NO (Short)
        beliefs = {"cand_0": 0.2}
        wealth = 100.0
        
        wagers = Strategy.beliefs_to_wagers(beliefs, wealth, state)
        
        asset_id, wager = wagers[0]
        self.assertTrue(wager < 0) # Negative wager (Buying NO)


if __name__ == '__main__':
    unittest.main()
