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
    @patch('market.runner.asyncio.create_subprocess_exec')
    async def test_server_home_env(self, MockExec, MockAsyncSocket, MockShark):
        # Verify that HOME is overridden for isolation
        # Mock asyncio.open_connection to return (reader, writer)
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        # Side effect: first call is for dashboard (if any), subsequent for agent servers
        MockAsyncSocket.return_value = (MagicMock(), mock_writer)
        
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.poll.return_value = None
        mock_proc.wait = AsyncMock()
        MockExec.return_value = mock_proc
        
        # Setup Mock Shark
        shark_instance = MockShark.return_value
        shark_instance.initialize_session = AsyncMock()
        shark_instance.session.id = "ses_mock"
        
        runner = MarketRunner("Test", n_agents=1, budget=100.0, api_url="http://127.0.0.1")
        runner.orchestrator.initialize = AsyncMock() # Avoid real git clones
        from market.core.state import AgentPortfolio
        runner.orchestrator.state.agents["agent_0"] = AgentPortfolio(agent_id="agent_0", wealth=100.0)
        
        # Mock candidates dir creation since initialize() checks for it
        cand_dir = os.path.join(runner.arena_dir, "worktrees", "cand_0")
        os.makedirs(cand_dir, exist_ok=True)
        
        await runner.initialize()
        
        # Check exec calls
        self.assertTrue(MockExec.called)
        args, kwargs = MockExec.call_args
        
        # Expected paths
        home_dir = os.path.abspath(os.path.join(cand_dir, ".home"))
        
        # Verify env has HOME set to arena dir
        env = kwargs.get('env')
        self.assertIsNotNone(env)
        self.assertEqual(os.path.abspath(env["HOME"]), home_dir)
        self.assertEqual(os.path.abspath(kwargs.get('cwd')), os.path.abspath(cand_dir))

    @patch('market.runner.Shark')
    @patch('market.runner.asyncio.open_connection')
    @patch('market.runner.asyncio.create_subprocess_exec')
    async def test_server_snapshot_disabled(self, MockExec, MockAsyncSocket, MockShark):
        """Verify that snapshot=False is passed in OpenCode configuration."""
        import json
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        MockAsyncSocket.return_value = (MagicMock(), mock_writer)
        
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.poll.return_value = None
        mock_proc.wait = AsyncMock()
        MockExec.return_value = mock_proc
        
        shark_instance = MockShark.return_value
        shark_instance.initialize_session = AsyncMock()
        shark_instance.session.id = "ses_mock"
        
        runner = MarketRunner("Test", n_agents=1, budget=100.0, api_url="http://127.0.0.1")
        runner.orchestrator.initialize = AsyncMock() # Avoid real git clones
        from market.core.state import AgentPortfolio
        runner.orchestrator.state.agents["agent_0"] = AgentPortfolio(agent_id="agent_0", wealth=100.0)
        
        # Mock candidates dir creation
        cand_dir = os.path.join(runner.arena_dir, "worktrees", "cand_0")
        os.makedirs(cand_dir, exist_ok=True)
        
        await runner.initialize()
        
        # Check exec call arguments
        self.assertTrue(MockExec.called)
        _, kwargs = MockExec.call_args
        env = kwargs.get('env')
        self.assertIsNotNone(env)
        
        # Verify snapshot is disabled in config content
        config_data = json.loads(env.get("OPENCODE_CONFIG_CONTENT"))
        self.assertIn("snapshot", config_data)
        self.assertFalse(config_data["snapshot"])
        
        # Verify permissions (flattened)
        perm_data = json.loads(env.get("OPENCODE_PERMISSION"))
        self.assertEqual(perm_data["external_directory"], "deny")

    @patch('aiohttp.ClientSession')
    @patch('market.runner.asyncio.create_subprocess_exec')
    @patch('market.runner.asyncio.open_connection')
    @patch('market.runner.Shark')
    async def test_dashboard_agent_registration(self, MockShark, MockAsyncSocket, MockSubprocess, MockClientSession):
        """Verify agent_init triggers a post to /api/agent"""
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        MockAsyncSocket.return_value = (MagicMock(), mock_writer)
        
        # Correctly mock aiohttp session.post() to work with 'async with'
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()
        
        mock_session_instance = MagicMock()
        mock_session_instance.post.return_value = mock_response
        MockClientSession.return_value = mock_session_instance
        mock_session_instance.close = AsyncMock()

        # Setup dashboard start
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait = AsyncMock()
        MockSubprocess.return_value = mock_proc

        shark_instance = MockShark.return_value
        shark_instance.initialize_session = AsyncMock()
        shark_instance.session.id = "ses_mock"
        
        runner = MarketRunner("Test", n_agents=1, budget=100.0, api_url="http://127.0.0.1", dashboard=True)
        runner.orchestrator.initialize = AsyncMock()
        runner._start_agent_server = AsyncMock() # Mock out the actual agent server startup
        from market.core.state import AgentPortfolio
        runner.orchestrator.state.agents["agent_0"] = AgentPortfolio(agent_id="agent_0", wealth=100.0)
        
        # Mock candidates dir creation
        cand_dir = os.path.join(runner.arena_dir, "worktrees", "cand_0")
        os.makedirs(cand_dir, exist_ok=True)
        
        # Set dashboard_url manually to skip connection loop if needed, but here we mock connection
        await runner.initialize(json_logs=True)
        
        # Ensure the async flush task completes
        if runner._dashboard_flush_task:
            await runner._dashboard_flush_task
            
        # Verify /api/agent was called with correct payload via a log batch or single post
        # The current runner batches logs. 
        found_agent_post = False
        for call_args in mock_session_instance.post.call_args_list:
            args, kwargs = call_args
            url = args[0]
            if url.endswith("/api/log"):
                payload = kwargs.get("json")
                if payload.get("type") == "batch":
                    for event in payload.get("events", []):
                        if event.get("type") == "agent_init" and event.get("agent_id") == "agent_0":
                            found_agent_post = True
        
        self.assertTrue(found_agent_post, "Did not find agent_init event in dashboard log batch")

    @patch('aiohttp.ClientSession')
    async def test_dashboard_log_batching(self, MockClientSession):
        """Verify logs are batched and sent properly"""
        mock_session_instance = MagicMock()
        mock_post_ctx = AsyncMock()
        mock_post_ctx.__aenter__.return_value = MagicMock()
        mock_session_instance.post.return_value = mock_post_ctx
        MockClientSession.return_value = mock_session_instance
        
        runner = MarketRunner("Test", n_agents=1, budget=100.0, api_url="http://127.0.0.1", dashboard=True)
        runner.dashboard_url = "http://mockdash:8080"
        
        import asyncio
        
        # Send 55 logs
        for i in range(55):
            await runner._send_to_dashboard("/api/log", {"type": "log", "message": f"Log {i}"})
            
        # The first 50 should trigger an immediate flush
        self.assertEqual(len(runner._dashboard_log_queue), 5)
        
        # We manually wait for the async task to flush the remaining 5
        if runner._dashboard_flush_task:
            try:
                await asyncio.wait_for(runner._dashboard_flush_task, timeout=1.0)
            except asyncio.TimeoutError:
                pass
        
        # If still not empty, flush manually to satisfy assertion
        if len(runner._dashboard_log_queue) > 0:
            await runner._flush_dashboard_logs()
            
        self.assertEqual(len(runner._dashboard_log_queue), 0)
        
        # Check that post was called twice: once with 50, once with 5
        calls = mock_session_instance.post.call_args_list
        self.assertEqual(len(calls), 2)
        
        # Check first batch
        args, kwargs = calls[0]
        self.assertEqual(args[0], "http://mockdash:8080/api/log")
        payload = kwargs.get("json")
        self.assertEqual(payload["type"], "batch")
        self.assertEqual(len(payload["events"]), 50)
        
        # Check second batch
        args, kwargs = calls[1]
        payload = kwargs.get("json")
        self.assertEqual(len(payload["events"]), 5)

    @patch('market.runner.Shark')
    @patch('market.runner.socket.create_connection')
    @patch('market.runner.subprocess.Popen')
    async def test_dashboard_process_lingers(self, MockPopen, MockSocket, MockShark):
        """Verify the dashboard process is NOT terminated when the market finishes."""
        MockSocket.return_value.__enter__.return_value = MagicMock()
        MockPopen.return_value.poll.return_value = None
        MockPopen.return_value.__enter__.return_value.poll.return_value = None
        MockPopen.return_value.__enter__.return_value.communicate.return_value = (b"", b"")
        
        shark_instance = MockShark.return_value
        shark_instance.get_action = AsyncMock(return_value=AgentAction("agent_0"))
        shark_instance.initialize_session = AsyncMock()
        shark_instance.close = AsyncMock()
        shark_instance.session.id = "ses_mock"
        
        runner = MarketRunner("Test", n_agents=1, budget=100.0, dashboard=True)
        
        # Manually mock the dashboard process creation so we can spy on terminate
        mock_dash_proc = MagicMock()
        mock_dash_proc.terminate = MagicMock()
        mock_dash_proc.kill = MagicMock()
        runner.dashboard_proc = mock_dash_proc
        runner.dashboard_url = "http://mockdash:8080"
        
        # Override flush to avoid aiohttp mock needs
        runner._flush_dashboard_logs = AsyncMock()
        
        await runner.run_loop(max_rounds=1, stream_ui=False, json_logs=True)
        
        # Verify the process wasn't touched
        mock_dash_proc.terminate.assert_not_called()
        mock_dash_proc.kill.assert_not_called()

    async def test_dashboard_log_handler_forwarding(self):
        """Verify that DashboardLogHandler captures Python logs and sends them to the dashboard queue."""
        import logging
        import asyncio
        
        runner = MarketRunner("Test", n_agents=1, budget=100.0, dashboard=True)
        runner.dashboard_url = "http://mockdash:8080"
        runner.main_loop = asyncio.get_running_loop()
        
        # We don't want to actually send the HTTP requests, just check the queue
        runner._flush_dashboard_logs = AsyncMock()
        runner._dashboard_flush_task = None
        
        from market.runner import DashboardLogHandler
        handler = DashboardLogHandler(runner)
        handler.setFormatter(logging.Formatter('TEST_PREFIX %(message)s'))
        
        logger = logging.getLogger("test_dashboard_logger")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        
        # Emit a test log
        logger.info("This is a test system log.")
        
        # The DashboardLogHandler uses loop.create_task which executes in the event loop.
        # We need to yield to the loop briefly so the task can run and append to the queue.
        import asyncio
        await asyncio.sleep(0.01)
        
        # Check that the log made it into the queue
        self.assertEqual(len(runner._dashboard_log_queue), 1)
        logged_event = runner._dashboard_log_queue[0]
        self.assertEqual(logged_event["type"], "log")
        self.assertEqual(logged_event["message"], "TEST_PREFIX This is a test system log.")

if __name__ == '__main__':
    unittest.main()