import unittest
from market.core.strategy import Strategy
from market.core.state import MarketState, MarketAsset

class StrategyTest(unittest.TestCase):
    
    def test_beliefs_to_trades(self):
        state = MarketState(round_num=1, liquidity_b=100.0)
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc")
        
        # Belief 0.8 > Price 0.5 -> Buy YES
        beliefs = {"cand_0": 0.8}
        wealth = 100.0
        
        trades = Strategy.beliefs_to_trades(beliefs, wealth, state)
        
        self.assertEqual(len(trades), 1)
        asset_id, delta_q = trades[0]
        self.assertEqual(asset_id, "cand_0")
        self.assertTrue(delta_q > 0) # Buying YES

    def test_shorting(self):
        state = MarketState(round_num=1, liquidity_b=100.0)
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc")
        
        # Belief 0.2 < Price 0.5 -> Sell YES (Short)
        beliefs = {"cand_0": 0.2}
        wealth = 100.0
        
        trades = Strategy.beliefs_to_trades(beliefs, wealth, state)
        
        asset_id, delta_q = trades[0]
        self.assertTrue(delta_q < 0) # Selling YES

if __name__ == '__main__':
    unittest.main()
