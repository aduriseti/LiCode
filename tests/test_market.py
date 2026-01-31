import unittest
from licode.market import MarketState, AgentState, SentenceData

class TestMarketState(unittest.TestCase):
    def setUp(self):
        self.agent_ids = ["agent1", "agent2"]
        self.initial_budget = 200.0
        self.market = MarketState(self.agent_ids, self.initial_budget)

    def test_initialization(self):
        # Agents should have split the budget
        self.assertEqual(self.market.agents["agent1"].wealth, 100.0)
        self.assertEqual(self.market.agents["agent2"].wealth, 100.0)
        
        # Whale should have sum of agents' wealth (200.0)
        self.assertTrue("whale" in self.market.agents)
        self.assertEqual(self.market.agents["whale"].wealth, 200.0)

    def test_register_sentence(self):
        s_id = self.market.register_sentence("Test Sentence")
        self.assertIn(s_id, self.market.sentences)
        self.assertEqual(self.market.sentences[s_id].text, "Test Sentence")
        self.assertEqual(self.market.sentences[s_id].current_price, 0.5)

    def test_submit_belief(self):
        s_id = self.market.register_sentence("Test Sentence")
        self.market.submit_belief("agent1", s_id, 0.8)
        self.assertEqual(self.market.sentences[s_id].beliefs["agent1"], 0.8)
        
        # Test clamping
        self.market.submit_belief("agent1", s_id, 1.5)
        self.assertLess(self.market.sentences[s_id].beliefs["agent1"], 1.0)
        
        self.market.submit_belief("agent1", s_id, -0.5)
        self.assertGreater(self.market.sentences[s_id].beliefs["agent1"], 0.0)

    def test_update_price(self):
        s_id = self.market.register_sentence("Test Sentence")
        
        # Agent 1 believes 0.9, Agent 2 believes 0.1
        # Initial price is 0.5.
        # Kelly fractions:
        # A1: (0.9 - 0.5) / (0.5 * 0.5) = 0.4 / 0.25 = 1.6
        # A2: (0.1 - 0.5) / (0.5 * 0.5) = -0.4 / 0.25 = -1.6
        # Kappas (assuming eta=0.1): 0.1 / max(1, 1.6) = 0.0625 for both
        # Wealths are equal (100).
        # Weighted avg should be roughly (0.9 + 0.1) / 2 = 0.5 if weights are equal.
        
        self.market.submit_belief("agent1", s_id, 0.9)
        self.market.submit_belief("agent2", s_id, 0.1)
        
        self.market.update_price(s_id)
        
        # Since symmetric beliefs and equal wealth, price should stay near 0.5
        # (Numerical precision might drift it slightly, but effectively 0.5)
        self.assertAlmostEqual(self.market.sentences[s_id].current_price, 0.5, delta=0.01)

        # Now make Agent 1 super rich
        self.market.agents["agent1"].wealth = 10000.0
        self.market.update_price(s_id)
        
        # Price should move towards Agent 1's belief (0.9)
        self.assertGreater(self.market.sentences[s_id].current_price, 0.7)

    def test_settlement_payout(self):
        s_id = self.market.register_sentence("Truth")
        self.market.sentences[s_id].current_price = 0.5
        
        # Agent 1 bets HIGH (correct)
        self.market.submit_belief("agent1", s_id, 0.9)
        # Agent 2 bets LOW (wrong)
        self.market.submit_belief("agent2", s_id, 0.1)
        
        initial_w1 = self.market.agents["agent1"].wealth
        initial_w2 = self.market.agents["agent2"].wealth
        
        self.market.settle_truth(s_id, True)
        
        # Agent 1 should gain, Agent 2 should lose
        self.assertGreater(self.market.agents["agent1"].wealth, initial_w1)
        self.assertLess(self.market.agents["agent2"].wealth, initial_w2)
        
        self.assertTrue(self.market.sentences[s_id].resolved_value)

    def test_whale_witness_trigger(self):
        # Scenario: Cand 1 fails test, Cand 2 passes.
        s_id_c1 = self.market.register_sentence("Cand 1 is good")
        
        # Whale is observing
        self.market.witness_trigger("cand1", "cand2", True, False, s_id_c1)
        
        # Whale should have bet approx 0.0 (clamped)
        self.assertAlmostEqual(self.market.sentences[s_id_c1].beliefs["whale"], 0.0, delta=1e-5)

    def test_rebalance_whale(self):
        self.market.agents["whale"].wealth = 0.0
        self.market.rebalance_whale()
        # Should be sum of agents (100 + 100 = 200)
        self.assertEqual(self.market.agents["whale"].wealth, 200.0)

if __name__ == '__main__':
    unittest.main()
