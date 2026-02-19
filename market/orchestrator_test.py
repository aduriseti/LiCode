import unittest
from market.orchestrator import Orchestrator, AgentAction

class TestOrchestrator(unittest.IsolatedAsyncioTestCase):
    
    async def test_basic_loop(self):
        # Init
        orch = Orchestrator("Solve X", n_agents=2, budget=1000.0)
        await orch.initialize()
        
        self.assertEqual(len(orch.state.agents), 2)
        self.assertEqual(len(orch.state.assets), 2) # 2 candidates
        
        # Initial prices should be 0.5 (1/N for N=2)
        p0 = orch.state.get_asset_price("cand_0")
        self.assertAlmostEqual(p0, 0.5)
        
        # Round 1: Agent 0 bets on themselves
        # Belief must be > p0 (0.5) to move price up.
        action_0 = AgentAction(
            agent_id="agent_0",
            beliefs={"cand_0": 0.7} 
        )
        
        await orch.process_round([action_0])
        
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

    async def test_whale_intervention(self):
        orch = Orchestrator("Solve X", n_agents=2)
        await orch.initialize()
        
        # Add a verifier manually
        from market.core.state import MarketAsset
        orch.state.assets["v1"] = MarketAsset(id="v1", type="VERIFIER", description="Manual V", q_yes=100) # Price > 0.5
        
        # Set failure
        orch.state.test_failures["v1:cand_0"] = True
        
        # Round 1
        await orch.process_round([])
        
        # Whale should have shorted cand_0
        p_cand0 = orch.state.get_asset_price("cand_0")
        self.assertTrue(p_cand0 < 0.5)

    async def test_pretty_summary(self):
        orch = Orchestrator("Display Test", n_agents=2)
        await orch.initialize()
        summary = orch.get_pretty_summary()
        
        # Verify basic structure
        self.assertIn("Round 0 Summary", summary)
        self.assertIn("Prices", summary)
        self.assertIn("cand_0", summary)
        self.assertIn("Whale Wealth", summary)
        
        # Verify it runs on a later round too
        orch.state.round_num = 10
        summary_10 = orch.get_pretty_summary()
        self.assertIn("Round 10 Summary", summary_10)

    async def test_symmetric_wealth_conservation(self):
        """Verify that Whale wealth is perfectly conserved during its own trades."""
        orch = Orchestrator("Test", n_agents=1, budget=1000.0)
        await orch.initialize()
        
        initial_whale_wealth = orch.state.whale_wealth
        
        # Simulate a Whale active trade (deductive)
        # Whale wants to buy 50 YES shares of cand_0
        trades = [("cand_0", 50.0)]
        orch._execute_trades("whale", trades)
        
        # Whale wealth should be EXACTLY the same (-cost + cost)
        self.assertEqual(orch.state.whale_wealth, initial_whale_wealth)
        # But price should have moved
        self.assertTrue(orch.state.get_asset_price("cand_0") > 0.5)

    async def test_agent_to_whale_transfer(self):
        """Verify that agent payments are correctly transferred to the Whale."""
        orch = Orchestrator("Test", n_agents=1, budget=1000.0)
        await orch.initialize()
        
        initial_whale_wealth = orch.state.whale_wealth
        initial_agent_wealth = orch.state.agents["agent_0"].wealth
        
        # Agent 0 buys 50 shares
        trades = [("cand_0", 50.0)]
        orch._execute_trades("agent_0", trades)
        
        agent_wealth_after = orch.state.agents["agent_0"].wealth
        whale_wealth_after = orch.state.whale_wealth
        
        cost = initial_agent_wealth - agent_wealth_after
        self.assertTrue(cost > 0)
        self.assertAlmostEqual(whale_wealth_after, initial_whale_wealth + cost, places=5)

if __name__ == '__main__':
    unittest.main()
