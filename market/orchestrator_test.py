import unittest
from market.orchestrator import Orchestrator, AgentAction

class TestOrchestrator(unittest.TestCase):
    
    def test_basic_loop(self):
        # Init
        orch = Orchestrator("Solve X", n_agents=2, budget=1000.0)
        
        self.assertEqual(len(orch.state.agents), 2)
        self.assertEqual(len(orch.state.assets), 2) # 2 candidates
        
        # Initial prices should be 0.5
        p0 = orch.state.get_asset_price("cand_0")
        self.assertAlmostEqual(p0, 0.5)
        
        # Round 1: Agent 0 bets on themselves
        # Reduced belief to avoid immediate bankruptcy via "all-in" + tax
        action_0 = AgentAction(
            agent_id="agent_0",
            beliefs={"cand_0": 0.55} 
        )
        
        orch.process_round([action_0])
        
        # Verify Price Move
        p1 = orch.state.get_asset_price("cand_0")
        self.assertTrue(p1 > 0.5)
        
        # Verify Wealth Change (Agent 0 paid for shares)
        if "agent_0" in orch.state.agents:
            w1 = orch.state.agents["agent_0"].wealth
            self.assertTrue(w1 < 500.0) 
            shares = orch.state.agents["agent_0"].shares["cand_0"]
            self.assertTrue(shares > 0)
        else:
            self.fail("Agent 0 went bankrupt too fast")

    def test_whale_intervention(self):
        orch = Orchestrator("Solve X", n_agents=2)
        
        # Add a verifier manually
        from market.core.state import MarketAsset
        orch.state.assets["v1"] = MarketAsset(id="v1", type="VERIFIER", description="Manual V", q_yes=100) # Price > 0.5
        
        # Set failure
        orch.state.test_failures["v1:cand_0"] = True
        
        # Round 1
        orch.process_round([])
        
        # Whale should have shorted cand_0
        p_cand0 = orch.state.get_asset_price("cand_0")
        self.assertTrue(p_cand0 < 0.5)

    def test_pretty_summary(self):
        orch = Orchestrator("Display Test", n_agents=2)
        summary = orch.get_pretty_summary()
        
        # Verify basic structure
        self.assertIn("ROUND 0", summary)
        self.assertIn("Asset", summary)
        self.assertIn("cand_0", summary)
        self.assertIn("Whale Wealth", summary)
        
        # Verify it runs on a later round too
        orch.state.round_num = 10
        summary_10 = orch.get_pretty_summary()
        self.assertIn("ROUND 10", summary_10)

if __name__ == '__main__':
    unittest.main()
