import math
import unittest

from market.core.lmsr import LMSRMarket
from market.core.state import MarketAsset, MarketState
from market.logic.whale import Whale
from market.orchestrator import AgentAction, Orchestrator


class TestDesignConformity(unittest.IsolatedAsyncioTestCase):
    async def test_liquidity_parameter(self):
        """Design 2.A.67: Fixed b = B / 20.0"""
        budget = 2000.0
        orch = Orchestrator("Test", n_agents=3, budget=budget)
        # In initialize, budget is used to set liquidity_b
        self.assertEqual(orch.state.liquidity_b, budget / 20.0)

    async def test_initial_candidate_price(self):
        """Design 2.B.118: Initial price 1/N for candidates"""
        n = 5
        budget = 1000.0
        orch = Orchestrator("Test", n_agents=n, budget=budget)
        await orch.initialize()

        for i in range(n):
            cid = f"cand_{i}"
            price = orch.state.get_asset_price(cid)
            self.assertAlmostEqual(price, 1.0 / n, places=5)

    async def test_whale_beliefs_softmax(self):
        """Design 2.C.179: Whale beliefs via Softmax of Log-Survival Scores"""
        state = MarketState(round_num=1, liquidity_b=100.0)
        state.assets["cand_0"] = MarketAsset(id="cand_0", type="CANDIDATE", description="C0")
        state.assets["cand_1"] = MarketAsset(id="cand_1", type="CANDIDATE", description="C1")
        state.assets["v1"] = MarketAsset(
            id="v1", type="VERIFIER", description="V1", q_yes=100.0
        )  # High validity P=0.73

        # P(v1) = e^1 / (e^1 + e^0) = 2.718 / 3.718 = 0.731
        p_v1 = LMSRMarket.current_price(100.0, 0.0, 100.0)

        # cand_0 fails v1
        state.test_failures["v1:cand_0"] = True

        scores = Whale.compute_survival_scores(state)
        # S_0 = ln(1 - P(v1))
        # S_1 = 0
        self.assertAlmostEqual(scores["cand_0"], math.log(1.0 - p_v1))
        self.assertEqual(scores["cand_1"], 0.0)

        beliefs = Whale.compute_whale_beliefs(scores)
        expected_b0 = math.exp(scores["cand_0"]) / (math.exp(scores["cand_0"]) + math.exp(0.0))
        self.assertAlmostEqual(beliefs["cand_0"], expected_b0)

    async def test_settlement_preserves_price(self):
        """Design 2.C.271: Settlement preserves price discovery"""
        orch = Orchestrator("Test", n_agents=1, budget=1000.0)
        await orch.initialize()

        aid = "agent_0"
        cid = "cand_0"

        # Agent bets 100 on cand_0
        action = AgentAction(aid, beliefs={cid: 0.9})
        await orch.process_round([action])

        price_after_trade = orch.state.get_asset_price(cid)
        self.assertGreater(price_after_trade, 0.5)

        # After settlement, agent shares should be 0 (except if in bond)
        # But price should remain same as price_after_trade
        self.assertNotIn(cid, orch.state.agents[aid].shares)
        self.assertAlmostEqual(orch.state.get_asset_price(cid), price_after_trade, places=5)

        # Whale should have absorbed the position
        self.assertIn(cid, orch.state.whale_shares)
        self.assertGreater(orch.state.whale_shares[cid], 0)


if __name__ == "__main__":
    unittest.main()
