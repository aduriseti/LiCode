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

    def test_no_short_at_max_confidence(self):
        """Verifies that agents do not short when both they and the market are at the confidence ceiling."""
        state = MarketState(round_num=1, liquidity_b=100.0)
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc")
        
        # 1. Force the market price to 1.0 (or very close)
        # In LMSR, P = e^(q_yes/b) / (e^(q_yes/b) + e^(q_no/b))
        # If q_yes is very large relative to b, P -> 1.0
        state.assets["cand_0"].q_yes = 10000.0 
        self.assertAlmostEqual(state.get_asset_price("cand_0"), 1.0, places=5)
        
        # 2. Agent has max belief (0.99)
        beliefs = {"cand_0": 0.99}
        wealth = 100.0
        
        # 3. Calculate wagers
        wagers = Strategy.beliefs_to_wagers(beliefs, wealth, state)
        
        # 4. Verify no wagers were created (Edge should be 0.99 - 0.99 = 0)
        self.assertEqual(len(wagers), 0, "No wagers should be created when belief and price are at max threshold")

    def test_no_long_at_min_confidence(self):
        """Verifies symmetric floor protection (no wagers when belief and price are at 0.01)."""
        state = MarketState(round_num=1, liquidity_b=100.0)
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc")
        
        # Force price to 0.0
        state.assets["cand_0"].q_no = 10000.0
        self.assertAlmostEqual(state.get_asset_price("cand_0"), 0.0, places=5)
        
        # Agent has min belief (0.01)
        beliefs = {"cand_0": 0.01}
        wealth = 100.0
        
        wagers = Strategy.beliefs_to_wagers(beliefs, wealth, state)
        self.assertEqual(len(wagers), 0, "No wagers should be created when belief and price are at min threshold")


if __name__ == '__main__':
    unittest.main()
