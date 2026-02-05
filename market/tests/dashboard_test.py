import unittest
from unittest.mock import MagicMock
from collections import deque
from rich.layout import Layout
from rich.console import Console

# Adjust import path as needed
from market.runner import MarketRunner
from market.core.state import MarketState, MarketAsset, AgentPortfolio

class TestDashboard(unittest.TestCase):
    def setUp(self):
        # Mock dependencies
        self.mock_orchestrator = MagicMock()
        self.mock_orchestrator.state = MarketState(
            round_num=1,
            liquidity_b=100.0,
            whale_wealth=1000.0
        )
        
        # Populate dummy data
        self.mock_orchestrator.state.assets = {
            "cand_0": MarketAsset(id="cand_0", type="CANDIDATE", description="Test Candidate"),
            "v_123": MarketAsset(id="v_123", type="VERIFIER", description="Test Verifier")
        }
        self.mock_orchestrator.state.agents = {
            "agent_0": AgentPortfolio(agent_id="agent_0", wealth=500.0)
        }
        # Mock get_asset_price
        self.mock_orchestrator.state.get_asset_price = MagicMock(return_value=0.5)

        # Create a partial runner instance without starting server
        # We manually construct it to avoid __init__ side effects like starting servers
        self.runner = MarketRunner.__new__(MarketRunner)
        self.runner.orchestrator = self.mock_orchestrator
        self.runner.sharks = {"agent_0": MagicMock()}
        self.runner.api_url = "http://mock-url"
        self.runner.log_buffer = deque(["Log 1", "Log 2"], maxlen=20)

    def test_render_dashboard_structure(self):
        """Verify the dashboard layout contains all expected panels."""
        layout = self.runner._render_dashboard()
        
        self.assertIsInstance(layout, Layout)
        
        # Check for main sections by name
        # Rich Layouts are tree structures; we can inspect children if named
        # Note: _render_dashboard splits columns/rows but might not assign names deep down
        # except for the top-level splits we defined: header, main, logs, footer
        
        # Accessing children by index or name if set
        # Our implementation does: layout.split_column(header, main, logs, footer)
        # So layout.children should have 4 elements
        self.assertEqual(len(layout.children), 4)
        
        names = [child.name for child in layout.children]
        self.assertIn("header", names)
        self.assertIn("main", names)
        self.assertIn("logs", names)
        self.assertIn("footer", names)

    def test_dashboard_content(self):
        """Render the dashboard to a string to check for key content."""
        layout = self.runner._render_dashboard()
        
        console = Console(width=100, record=True)
        console.print(layout)
        output = console.export_text()
        
        # Check Header
        self.assertIn("Round 1", output)
        self.assertIn("Whale Wealth: 1000.00", output)
        
        # Check Assets
        self.assertIn("cand_0", output)
        self.assertIn("v_123", output)
        
        # Check Agents
        self.assertIn("agent_0", output)
        self.assertIn("500.00", output)
        
        # Check Logs
        self.assertIn("Log 1", output)
        self.assertIn("Log 2", output)
        
        # Check Footer / Attach Command
        self.assertIn("opencode attach http://mock-url", output)

if __name__ == '__main__':
    unittest.main()
