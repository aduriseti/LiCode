import unittest
from market.core.state import MarketState, MarketAsset
from market.logic.whale import Whale

class TestWhale(unittest.TestCase):
    
    def setUp(self):
        self.state = MarketState(round_num=1, liquidity_b=100.0)
        
        # Add 3 Candidates
        for i in range(3):
            cid = f"cand_{i}"
            self.state.assets[cid] = MarketAsset(id=cid, type="CANDIDATE", description=f"C{i}")
            
        # Add 2 Verifiers
        # V1: High validity (Market believes it's a good test)
        # To get P ~ 0.99, we need q_yes >> q_no
        # ln(0.99/0.01) * 100 = 4.59 * 100 = 459
        self.state.assets["v_high"] = MarketAsset(id="v_high", type="VERIFIER", description="Good Test", q_yes=460)
        
        # V2: Low validity (Market thinks it's garbage)
        # P ~ 0.01
        self.state.assets["v_low"] = MarketAsset(id="v_low", type="VERIFIER", description="Bad Test", q_yes=-460)

    def test_survival_logic(self):
        # Case 1: Cand_0 fails High Validity test
        # Should get crushed
        self.state.test_failures["v_high:cand_0"] = True
        
        scores = Whale.compute_survival_scores(self.state)
        
        # S_0 should be ln(1 - 0.99) approx ln(0.01) = -4.6
        # S_1, S_2 should be 0 (no failures)
        
        self.assertTrue(scores["cand_0"] < -3.0)
        self.assertEqual(scores["cand_1"], 0.0)
        
        beliefs = Whale.compute_whale_beliefs(scores)
        
        # Cand 0 belief should be near zero
        self.assertTrue(beliefs["cand_0"] < 0.05)
        # Cand 1 and 2 should split the rest (~0.5 each)
        self.assertAlmostEqual(beliefs["cand_1"], beliefs["cand_2"], places=1)
        self.assertTrue(beliefs["cand_1"] > 0.4)

    def test_ignore_garbage_tests(self):
        # Case 2: Cand_0 fails Low Validity test
        # Should be mostly ignored
        self.state.test_failures["v_low:cand_0"] = True
        
        scores = Whale.compute_survival_scores(self.state)
        
        # P(v_low) ~ 0.01
        # S_0 = ln(1 - 0.01) = ln(0.99) ~ -0.01
        
        self.assertTrue(scores["cand_0"] > -0.1) # Barely penalized
        self.assertTrue(scores["cand_0"] < 0.0)
        
        beliefs = Whale.compute_whale_beliefs(scores)
        
        # Beliefs should be roughly equal (0.33 each)
        self.assertAlmostEqual(beliefs["cand_0"], 0.33, delta=0.05)

if __name__ == '__main__':
    unittest.main()
