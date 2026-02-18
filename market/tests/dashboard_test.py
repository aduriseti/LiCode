import unittest
from unittest.mock import MagicMock
from collections import deque
import sys
import os

# Adjust import path
from market.runner import MarketRunner
from market.core.state import MarketState, MarketAsset, AgentPortfolio
from market.orchestrator import Orchestrator

class TestDashboard(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Mock State
        self.state = MarketState(
            round_num=1,
            liquidity_b=100.0,
            whale_wealth=1000.0,
            prompt="Test Prompt"
        )
        self.state.assets = {
            "cand_0": MarketAsset(id="cand_0", type="CANDIDATE", description="Test Candidate"),
            "v_123": MarketAsset(id="v_123", type="VERIFIER", description="Test Verifier")
        }
        self.state.agents = {
            "agent_0": AgentPortfolio(agent_id="agent_0", wealth=500.0)
        }
        
        # Initialize Orchestrator with mocked state
        self.orchestrator = Orchestrator("Test", 1, 1000.0, state=self.state)
        await self.orchestrator.initialize()

    async def test_dashboard_content(self):
        """Render the text dashboard to check for key content."""
        output = self.orchestrator.get_pretty_summary()
        
        # Check Header
        self.assertIn("Round 1", output)
        # Note: Whitespace matching might be fragile, so check distinct parts
        self.assertIn("Whale Wealth:", output)
        self.assertIn("1000.00", output)
        
        # Check Assets
        self.assertIn("cand_0", output)
        self.assertIn("v_123", output)
        
        # Check Agents
        self.assertIn("agent_0", output)
        self.assertIn("1000.00", output)
        
        # Check Formatting (Plain text)
        self.assertIn("--- Round 1 Summary ---", output)
        self.assertIn("Market Prices:", output)

if __name__ == '__main__':
    unittest.main()