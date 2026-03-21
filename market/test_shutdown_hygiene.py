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

    @patch('market.runner.Shark')
    @patch('market.runner.socket.create_connection')
    @patch('market.runner.asyncio.open_connection')
    @patch('market.runner.market.common.process_registry.registry.spawn')
    async def test_graceful_shutdown_prevents_loop_error(self, MockSpawn, MockAsyncSocket, MockSocket, MockShark):
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

        MockSpawn.return_value.__aenter__.return_value = MagicMock(pid=9999, returncode=None)
        MockSpawn.return_value.__aexit__ = AsyncMock()
        
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
        
        # Verify that ExitStack was used for cleanup
        # We don't need to check mock_killpg anymore as process_registry handles it.
        
        # If we reached here without a RuntimeError, the fix is likely working 

    @patch('market.runner.Shark')
    @patch('market.runner.socket.create_connection')
    @patch('market.runner.asyncio.open_connection')
    @patch('market.runner.market.common.process_registry.registry.spawn')
    async def test_shutdown_on_exception(self, MockSpawn, MockAsyncSocket, MockSocket, MockShark):
        """
        Verifies that even if an exception occurs during the tournament, 
        shark clients are still closed.
        """
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        MockAsyncSocket.return_value = (MagicMock(), mock_writer)
        
        MockSocket.return_value.__enter__.return_value = MagicMock()

        MockSpawn.return_value.__aenter__.return_value = MagicMock(pid=9999, returncode=None)
        MockSpawn.return_value.__aexit__ = AsyncMock()
        
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