import unittest
from licode.market import MarketState
from licode.orchestrator import Orchestrator
from licode.agent import Agent, Move
import asyncio
from unittest.mock import AsyncMock

class TestEconomics(unittest.TestCase):
    def test_deduct_round_costs(self):
        # Setup market
        market = MarketState(["a1", "a2"], 200.0)
        # Initial wealth 100 each
        self.assertEqual(market.agents["a1"].wealth, 100.0)
        
        # Deduct costs
        costs = {"a1": 5.0, "a2": 10.0}
        market.deduct_round_costs(costs)
        
        self.assertEqual(market.agents["a1"].wealth, 95.0)
        self.assertEqual(market.agents["a2"].wealth, 90.0)

    def test_bankruptcy_trigger(self):
        market = MarketState(["a1"], 10.0)
        # Initial 10.0
        
        # Deduct massive cost
        market.deduct_round_costs({"a1": 9.5}) # Wealth -> 0.5 (< 1.0)
        
        self.assertTrue(market.agents["a1"].is_bankrupt)
        self.assertEqual(market.agents["a1"].wealth, 0.5)
        
        # Deduct more - should not change wealth if bankrupt check prevents it?
        # My implementation of deduct_round_costs checks "if not agent.is_bankrupt"
        market.deduct_round_costs({"a1": 100.0})
        
        self.assertEqual(market.agents["a1"].wealth, 0.5)

    def test_orchestrator_cost_flow(self):
        orch = Orchestrator("test", agent_count=2, budget=200.0)
        
        # Mock agents to return specific costs
        move1 = Move(inference_cost=2.5)
        move2 = Move(inference_cost=3.0)
        
        orch.agents[0].get_next_move = AsyncMock(return_value=move1)
        orch.agents[1].get_next_move = AsyncMock(return_value=move2)
        
        # Run tick
        asyncio.run(orch.tick())
        
        # Check wealth
        # Initial 100.0
        w1 = orch.market.agents["minnow_0"].wealth
        w2 = orch.market.agents["minnow_1"].wealth
        
        self.assertEqual(w1, 97.5) # 100 - 2.5
        self.assertEqual(w2, 97.0) # 100 - 3.0
        
        orch.cleanup()

if __name__ == '__main__':
    unittest.main()
