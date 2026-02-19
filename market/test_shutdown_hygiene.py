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
    @patch('market.runner.subprocess.Popen')
    async def test_graceful_shutdown_prevents_loop_error(self, MockPopen, MockAsyncSocket, MockSocket, MockShark):
        """
        Verifies that MarketRunner closes all Shark clients before exiting its async loop.
        This prevents the 'RuntimeError: Event loop is closed' observed during cleanup.
        """
        # 1. Setup mocks
        mock_writer = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        MockAsyncSocket.return_value = (MagicMock(), mock_writer)
        
        MockSocket.return_value.__enter__.return_value = MagicMock()
        MockPopen.return_value.poll.return_value = None
        MockPopen.return_value.__enter__.return_value.poll.return_value = None
        MockPopen.return_value.__enter__.return_value.communicate.return_value = (b"", b"")
        
        shark_instance = MagicMock()
        shark_instance.get_action = AsyncMock(return_value=AgentAction("agent_0"))
        shark_instance.initialize_session = AsyncMock()
        shark_instance.session = MagicMock()
        shark_instance.session.id = "ses_123"
        shark_instance.log_path = "/tmp/agent_0.log"
        shark_instance.close = AsyncMock() # This is what we are testing
        
        MockShark.return_value = shark_instance

        # 2. Initialize Runner
        runner = MarketRunner(
            prompt="Shutdown Test",
            n_agents=1,
            budget=100.0,
            api_url="http://127.0.0.1"
        )
        await runner.initialize(json_logs=True)

        # 3. Execute run_loop
        # We use a short timeout and 1 round
        await runner.run_loop(max_rounds=1, stream_ui=False, json_logs=True)

        # 4. Verify hygiene
        # Ensure shark.close() was called BEFORE the test finished (while loop was active)
        shark_instance.close.assert_called_once()
        
        # If we reached here without a RuntimeError, the fix is likely working 
        # (though in a test environment the loop might be managed differently).
        # The explicit assertion of close() is the most reliable proxy for the fix.

    @patch('market.runner.Shark')
    @patch('market.runner.socket.create_connection')
    @patch('market.runner.asyncio.open_connection')
    @patch('market.runner.subprocess.Popen')
    async def test_shutdown_on_exception(self, MockPopen, MockAsyncSocket, MockSocket, MockShark):
        """
        Verifies that even if an exception occurs during the tournament, 
        shark clients are still closed.
        """
        mock_writer = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        MockAsyncSocket.return_value = (MagicMock(), mock_writer)
        
        MockSocket.return_value.__enter__.return_value = MagicMock()
        MockPopen.return_value.poll.return_value = None
        MockPopen.return_value.__enter__.return_value.poll.return_value = None
        MockPopen.return_value.__enter__.return_value.communicate.return_value = (b"", b"")
        
        shark_instance = MagicMock()
        shark_instance.get_action = AsyncMock(side_effect=RuntimeError("API Failure"))
        shark_instance.initialize_session = AsyncMock()
        shark_instance.session = MagicMock()
        shark_instance.session.id = "ses_123"
        shark_instance.log_path = "/tmp/agent_0.log"
        shark_instance.close = AsyncMock()
        
        MockShark.return_value = shark_instance
        
        runner = MarketRunner("Test", n_agents=1, budget=100.0, api_url="http://127.0.0.1")
        await runner.initialize(json_logs=True)
        
        with self.assertRaises(RuntimeError):
            await runner.run_loop(max_rounds=1, stream_ui=False, json_logs=True)
            
        shark_instance.close.assert_called_once()

if __name__ == '__main__':
    unittest.main()