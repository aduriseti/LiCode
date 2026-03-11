import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from market.runner import MarketRunner
from market.orchestrator import AgentAction

class TestShutdownHygiene(unittest.IsolatedAsyncioTestCase):
    """
    Tests focused on graceful shutdown and resource cleanup.
    Ensures that event loops are not closed before all async resources (like Shark clients) are finished.
    """

    @patch('os.killpg')
    @patch('os.getpgid', return_value=12345)
    @patch('market.runner.Shark')
    @patch('market.runner.socket.create_connection')
    @patch('market.runner.asyncio.open_connection')
    @patch('market.runner.asyncio.create_subprocess_exec')
    async def test_graceful_shutdown_prevents_loop_error(self, MockExec, MockAsyncSocket, MockSocket, MockShark, mock_getpgid, mock_killpg):
        """
        Verifies that MarketRunner closes all Shark clients before exiting its async loop.
        This prevents the 'RuntimeError: Event loop is closed' observed during cleanup.
        """
        # 1. Setup mocks
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        MockAsyncSocket.return_value = (MagicMock(), mock_writer)
        
        MockSocket.return_value.__enter__.return_value = MagicMock()
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        mock_proc.returncode = None
        mock_proc.poll.return_value = None
        mock_proc.wait = AsyncMock()
        MockExec.return_value = mock_proc
        
        shark_instance = MagicMock()
        shark_instance.get_action = AsyncMock(return_value=AgentAction("agent_0"))
        shark_instance.initialize_session = AsyncMock()
        shark_instance.session = MagicMock()
        shark_instance.session.id = "ses_123"
        shark_instance.log_path = "/tmp/agent_0.log"
        shark_instance.close = AsyncMock()
        shark_instance.shutdown = AsyncMock()
        
        MockShark.return_value = shark_instance

        # 2. Initialize Runner
        runner = MarketRunner(
            prompt="Shutdown Test",
            n_agents=1,
            budget=100.0,
            api_url="http://127.0.0.1"
        )
        runner.orchestrator.initialize = AsyncMock()
        from market.core.state import AgentPortfolio
        runner.orchestrator.state.agents["agent_0"] = AgentPortfolio(agent_id="agent_0", wealth=100.0)
        import os
        import signal
        os.makedirs(os.path.join(runner.arena_dir, "worktrees", "cand_0"), exist_ok=True)
        
        await runner.initialize(json_logs=True)

        # 3. Execute run_loop
        # We use a short timeout and 1 round
        await runner.run_loop(max_rounds=1, stream_ui=False, json_logs=True)
        
        # Call close to trigger server shutdown
        await runner.close()

        # 4. Verify hygiene
        # Ensure shark.shutdown() was called BEFORE the test finished (while loop was active)
        shark_instance.shutdown.assert_called_once()
        
        # Verify that process group termination was attempted
        mock_killpg.assert_called_with(12345, signal.SIGTERM)
        
        # If we reached here without a RuntimeError, the fix is likely working 
        # (though in a test environment the loop might be managed differently).
        # The explicit assertion of close() is the most reliable proxy for the fix.

    @patch('os.killpg')
    @patch('os.getpgid', return_value=12345)
    def test_stop_servers_kills_process_group(self, mock_getpgid, mock_killpg):
        runner = MarketRunner("Test", n_agents=1, budget=100.0, api_url="http://127.0.0.1")
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        runner.agent_servers["agent_0"] = mock_proc
        
        import signal
        runner._stop_servers()
        
        mock_getpgid.assert_called_once_with(9999)
        mock_killpg.assert_called_once_with(12345, signal.SIGTERM)
        self.assertEqual(len(runner.agent_servers), 0)

    @patch('market.runner.Shark')
    @patch('market.runner.socket.create_connection')
    @patch('market.runner.asyncio.open_connection')
    @patch('market.runner.asyncio.create_subprocess_exec')
    async def test_shutdown_on_exception(self, MockExec, MockAsyncSocket, MockSocket, MockShark):
        """
        Verifies that even if an exception occurs during the tournament, 
        shark clients are still closed.
        """
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        MockAsyncSocket.return_value = (MagicMock(), mock_writer)
        
        MockSocket.return_value.__enter__.return_value = MagicMock()
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.poll.return_value = None
        mock_proc.wait = AsyncMock()
        MockExec.return_value = mock_proc
        
        shark_instance = MagicMock()
        shark_instance.get_action = AsyncMock(side_effect=RuntimeError("API Failure"))
        shark_instance.initialize_session = AsyncMock()
        shark_instance.session = MagicMock()
        shark_instance.session.id = "ses_123"
        shark_instance.log_path = "/tmp/agent_0.log"
        shark_instance.close = AsyncMock()
        shark_instance.shutdown = AsyncMock()
        
        MockShark.return_value = shark_instance
        
        runner = MarketRunner("Test", n_agents=1, budget=100.0, api_url="http://127.0.0.1")
        runner.orchestrator.initialize = AsyncMock()
        from market.core.state import AgentPortfolio
        runner.orchestrator.state.agents["agent_0"] = AgentPortfolio(agent_id="agent_0", wealth=100.0)
        import os
        os.makedirs(os.path.join(runner.arena_dir, "worktrees", "cand_0"), exist_ok=True)
        
        await runner.initialize(json_logs=True)
        
        # EXPECTATION: The loop should now complete even if an agent fails,
        # so we don't expect RuntimeError to be raised here anymore.
        await runner.run_loop(max_rounds=1, stream_ui=False, json_logs=True)
            
        # Verify that failure was recorded and agent was still shutdown.
        self.assertEqual(runner.orchestrator.state.agents["agent_0"].failure_count, 1)
        shark_instance.shutdown.assert_called_once()

if __name__ == '__main__':
    unittest.main()