import unittest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from market.runner import MarketRunner
from market.orchestrator import AgentAction

class TestMarketRunner(unittest.IsolatedAsyncioTestCase):
    
    @patch('market.runner.Shark')
    @patch('market.runner.socket.create_connection')
    @patch('market.runner.subprocess.Popen')
    async def test_run_loop_basics(self, MockPopen, MockSocket, MockShark):
        # Mock server ready
        MockSocket.return_value.__enter__.return_value = MagicMock()
        MockPopen.return_value.poll.return_value = None
        MockPopen.return_value.__enter__.return_value.poll.return_value = None
        MockPopen.return_value.__enter__.return_value.communicate.return_value = (b"", b"")
        
        # Setup Mock Shark behavior
        shark_instance = MockShark.return_value
        shark_instance.get_action = AsyncMock(return_value=AgentAction("agent_0"))
        shark_instance.initialize_session = AsyncMock()
        shark_instance.close = AsyncMock()
        shark_instance.session.id = "ses_mock_123"
        
        runner = MarketRunner("Test", n_agents=2, budget=100.0, api_url="http://mock")
        await runner.run_loop(max_rounds=1, stream_ui=False)
        
        # Verify it ran 1 round
        self.assertEqual(runner.orchestrator.state.round_num, 1)
        
        @patch('market.runner.Shark')
        @patch('market.runner.socket.create_connection')
        async def test_convergence_bankruptcy(self, MockSocket, MockShark):
            MockSocket.return_value.__enter__.return_value = MagicMock()
            budget = 100.0
            runner = MarketRunner("Test", n_agents=2, budget=budget, api_url="http://mock")
        
            # Manually initialize agents (simulating runner.initialize() without its side effects)
            from market.core.state import AgentPortfolio
            # New threshold is 0.1 * B. For budget 100, threshold is 10.0.
            # Set total wealth to 9.0 (sum of 4.5 + 4.5) to trigger bankruptcy convergence.
            runner.orchestrator.state.agents["agent_0"] = AgentPortfolio(agent_id="agent_0", wealth=4.5)
            runner.orchestrator.state.agents["agent_1"] = AgentPortfolio(agent_id="agent_1", wealth=4.5)
        
            is_converged = runner.check_convergence()
            self.assertTrue(is_converged)
    @patch('market.runner.Shark')
    def test_convergence_stability(self, MockShark):
        runner = MarketRunner("Test", n_agents=2, budget=1000.0, api_url="http://mock")
        
        # Manually initialize agents and assets
        from market.core.state import AgentPortfolio, MarketAsset
        runner.orchestrator.state.agents["agent_0"] = AgentPortfolio(agent_id="agent_0", wealth=500.0)
        runner.orchestrator.state.agents["agent_1"] = AgentPortfolio(agent_id="agent_1", wealth=500.0)
        runner.orchestrator.state.assets["cand_0"] = MarketAsset(id="cand_0", type="CANDIDATE", description="Test")
        runner.orchestrator.state.assets["cand_1"] = MarketAsset(id="cand_1", type="CANDIDATE", description="Test")
        
        # Inject fake price history (stable)
        # Price history is list of dicts {cid: price}
        stable_prices = {"cand_0": 0.5, "cand_1": 0.5}
        
        # Add 10 identical rounds
        for _ in range(10):
            runner.price_history.append(stable_prices)
            
        is_converged = runner.check_convergence()
        self.assertTrue(is_converged)
        
        # Now make it volatile
        runner.price_history = []
        for i in range(10):
            p = 0.5 + (0.1 if i % 2 == 0 else -0.1) # Alternating 0.6, 0.4
            runner.price_history.append({"cand_0": p, "cand_1": 0.5})
            
        is_converged = runner.check_convergence()
        self.assertFalse(is_converged)

    @patch('market.runner.Shark')
    @patch('market.runner.asyncio.open_connection')
    @patch('market.runner.subprocess.Popen')
    async def test_server_home_env(self, MockPopen, MockAsyncSocket, MockShark):
        # Verify that HOME is overridden for isolation
        # Mock asyncio.open_connection to return (reader, writer)
        mock_writer = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        MockAsyncSocket.return_value = (MagicMock(), mock_writer)
        
        MockPopen.return_value.poll.return_value = None
        MockPopen.return_value.__enter__.return_value.poll.return_value = None
        MockPopen.return_value.__enter__.return_value.communicate.return_value = (b"", b"")
        
        # Setup Mock Shark
        shark_instance = MockShark.return_value
        shark_instance.initialize_session = AsyncMock()
        shark_instance.session.id = "ses_mock"
        
        runner = MarketRunner("Test", n_agents=1, budget=100.0, api_url="http://127.0.0.1")
        runner.orchestrator.initialize = AsyncMock() # Avoid real git clones
        from market.core.state import AgentPortfolio
        runner.orchestrator.state.agents["agent_0"] = AgentPortfolio(agent_id="agent_0", wealth=100.0)
        await runner.initialize()
        
        # Check Popen calls
        self.assertTrue(MockPopen.called)
        args, kwargs = MockPopen.call_args
        
        # Expected paths
        cand_dir = os.path.join(runner.arena_dir, "worktrees", "cand_0")
        home_dir = os.path.join(cand_dir, ".home")
        
        # Verify env has HOME set to arena dir
        env = kwargs.get('env')
        self.assertIsNotNone(env)
        self.assertEqual(env["HOME"], home_dir)
        self.assertEqual(kwargs.get('cwd'), cand_dir)

    @patch('market.runner.Shark')
    @patch('market.runner.asyncio.open_connection')
    @patch('market.runner.subprocess.Popen')
    async def test_server_snapshot_disabled(self, MockPopen, MockAsyncSocket, MockShark):
        """Verify that snapshot=False is passed in OpenCode configuration."""
        import json
        mock_writer = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        MockAsyncSocket.return_value = (MagicMock(), mock_writer)
        
        MockPopen.return_value.poll.return_value = None
        
        shark_instance = MockShark.return_value
        shark_instance.initialize_session = AsyncMock()
        shark_instance.session.id = "ses_mock"
        
        runner = MarketRunner("Test", n_agents=1, budget=100.0, api_url="http://127.0.0.1")
        runner.orchestrator.initialize = AsyncMock() # Avoid real git clones
        from market.core.state import AgentPortfolio
        runner.orchestrator.state.agents["agent_0"] = AgentPortfolio(agent_id="agent_0", wealth=100.0)
        await runner.initialize()
        
        # Check Popen call arguments
        self.assertTrue(MockPopen.called)
        _, kwargs = MockPopen.call_args
        env = kwargs.get('env')
        self.assertIsNotNone(env)
        
        # Verify snapshot is disabled in both env vars
        for var in ["OPENCODE_CONFIG_CONTENT", "OPENCODE_PERMISSION"]:
            config_data = json.loads(env.get(var))
            self.assertIn("snapshot", config_data)
            self.assertFalse(config_data["snapshot"], f"Snapshot should be False in {var}")

if __name__ == '__main__':
    unittest.main()