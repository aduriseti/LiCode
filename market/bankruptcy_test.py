import unittest
from unittest import mock
import os
import shutil
import tempfile
from market.orchestrator import Orchestrator, AgentAction
from market.core.state import MarketState, AgentPortfolio, MarketAsset, MarketBond

class TestBankruptcyLogic(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.state = MarketState(
            round_num=0,
            liquidity_b=100.0,
            whale_wealth=2000.0,
            prompt="test"
        )
        self.orch = Orchestrator("test", 1, state=self.state, base_dir=self.test_dir)
        await self.orch.initialize()
        # Initialize creates agent_0 and cand_0
        self.agent_id = "agent_0"
        self.agent = self.state.agents[self.agent_id]
        self.orch.inference_tax = 10.0 # Set a fixed tax for testing

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir)

    async def test_agent_survives_with_bonds(self):
        """Verifies agent stays alive if bond value + wealth > tax, even if wealth < tax."""
        # 1. Setup: Low liquid wealth ($5), but high bond value
        self.agent.wealth = 5.0
        
        # Add a verifier asset
        vid = "v1"
        self.state.assets[vid] = MarketAsset(id=vid, type="VERIFIER", description="Test", q_yes=100.0)
        # Price will be high (~0.73 with b=100)
        price = self.state.get_asset_price(vid)
        
        # Add a bond for 100 shares
        self.state.bonds.append(MarketBond(
            agent_id=self.agent_id,
            asset_id=vid,
            q_shares=100.0,
            unlock_round=10
        ))
        
        # Total Net Worth = 5.0 + (100 * 0.73) = 78.0 > Tax (10.0)
        
        # 2. Run Process Round (Step 7: Bankruptcy)
        # We call process_round with empty actions to trigger the logic
        with mock.patch.object(self.orch, '_run_oracle', new_callable=mock.AsyncMock):
            await self.orch.process_round([])
            
        # 3. Verify
        self.assertIn(self.agent_id, self.state.agents, "Agent should NOT be bankrupt")
        self.assertEqual(self.agent.wealth, -5.0, "Wealth should be 5 - 10 = -5")

    async def test_agent_bankrupts_when_total_value_low(self):
        """Verifies agent bankrupts if bond value + wealth <= tax."""
        # 1. Setup: Liquid wealth $2, Bond value $5 (10 shares at $0.5)
        self.agent.wealth = 2.0
        
        vid = "v1"
        self.state.assets[vid] = MarketAsset(id=vid, type="VERIFIER", description="Test", q_yes=0.0, q_no=0.0)
        # Price is 0.5
        
        self.state.bonds.append(MarketBond(
            agent_id=self.agent_id,
            asset_id=vid,
            q_shares=10.0,
            unlock_round=10
        ))
        
        # Total Net Worth = 2.0 + 5.0 = 7.0 <= Tax (10.0)
        
        # 2. Run Process Round
        with mock.patch.object(self.orch, '_run_oracle', new_callable=mock.AsyncMock):
            await self.orch.process_round([])
            
        # 3. Verify
        self.assertNotIn(self.agent_id, self.state.agents, "Agent SHOULD be bankrupt")
        # Bond should be liquidated
        self.assertEqual(len(self.state.bonds), 0)
        # Price should have moved back due to liquidation (Selling 10 shares)
        # Initial q_yes=0, q_no=0 -> price 0.5. 
        # Bond liquidation is delta_q = -10.
        # This will move price down.

if __name__ == "__main__":
    unittest.main()
