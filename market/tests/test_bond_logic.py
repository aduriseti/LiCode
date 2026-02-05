
import unittest
import os
import shutil
from market.core.state import MarketState, AgentPortfolio, MarketAsset, MarketBond
from market.orchestrator import Orchestrator

class TestBondLogic(unittest.TestCase):

    def setUp(self):
        self.test_dir = "/tmp/market_test_bond"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)
        
        self.state = MarketState(
            round_num=0,
            liquidity_b=100.0,
            whale_wealth=2000.0,
            prompt="test"
        )
        self.state.agents["agent1"] = AgentPortfolio(agent_id="agent1", wealth=1000.0)
        self.orch = Orchestrator("test", 1, state=self.state, base_dir=self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_bond_lifecycle(self):
        # 1. Create Verifier (Implicitly creates Bond)
        # Manually invoke _create_verifier logic partially or mock it
        # Actually, let's just use _create_verifier if we can mock the proposal
        
        proposal = {
            "type": "VERIFIER",
            "code": "print('hello')",
            "files": {"run.sh": "#!/bin/bash\necho hello"}
        }
        
        # This will create a bond via Strategy logic
        vid = self.orch._create_verifier("agent1", proposal)
        self.assertIsNotNone(vid)
        
        # Check Bond exists
        self.assertEqual(len(self.state.bonds), 1)
        bond = self.state.bonds[0]
        self.assertEqual(bond.agent_id, "agent1")
        self.assertEqual(bond.asset_id, vid)
        self.assertTrue(bond.q_shares > 0)
        
        # Check Agent Shares
        shares = self.state.agents["agent1"].shares.get(vid, 0.0)
        self.assertAlmostEqual(shares, bond.q_shares)
        
        # Check Cost (Wealth should decrease)
        self.assertTrue(self.state.agents["agent1"].wealth < 1000.0)
        
        # 2. Advance Round (Matures immediately if lock=1 and next round is 1)
        self.state.round_num += 1
        self.orch._mature_bonds()
        
        # Should be matured now (unlock=1, round=1)
        self.assertEqual(len(self.state.bonds), 0)
        
        # 3. Verify Payout
        shares_after = self.state.agents["agent1"].shares.get(vid, 0.0)
        self.assertAlmostEqual(shares_after, 0.0)
        
        final_wealth = self.state.agents["agent1"].wealth
        # LMSR is path independent. Buying X then Selling X returns to original state if b is constant.
        self.assertAlmostEqual(final_wealth, 1000.0, places=4)

if __name__ == '__main__':
    unittest.main()
