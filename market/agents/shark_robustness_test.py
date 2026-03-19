import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
import logging
from market.agents.shark import Shark, FatalAgentError
from market.core.state import MarketState
from market.orchestrator import AgentAction
from opencode_ai import APITimeoutError, APIConnectionError

class SharkRobustnessTest(unittest.IsolatedAsyncioTestCase):
    """
    Tests for Shark agent robustness features: retries and fallbacks.
    """

    @patch('market.agents.shark.AsyncOpencode')
    async def test_get_action_fallback_on_max_retries_exceeded(self, MockClient):
        # Setup Shark with 1 retry
        shark = Shark("agent_0", max_retries=1, timeout=1.0)
        shark.initialize_session = AsyncMock()
        shark.session = MagicMock()
        shark.session.id = "ses_123"
        shark.interrupt = AsyncMock()
        
        # Mock chat_robust to always timeout
        with patch.object(Shark, 'chat_robust') as mock_chat:
            mock_chat.side_effect = APITimeoutError("Timeout")
            
            state = MarketState(round_num=1, liquidity_b=100.0)
            
            # EXPECTATION: It should NOT raise FatalAgentError, but return empty AgentAction
            action = await shark.get_action(state)
            
            self.assertIsInstance(action, AgentAction)
            self.assertEqual(action.agent_id, "agent_0")
            self.assertEqual(action.beliefs, {})
            self.assertEqual(action.proposals, [])
            self.assertEqual(mock_chat.call_count, 2) # initial + 1 retry

    @patch('market.agents.shark.AsyncOpencode')
    async def test_get_action_fallback_on_parsing_failure(self, MockClient):
        # Parsing error allows max_total_attempts + 3 iterations (1 + 1 + 3 = 5 total)
        shark = Shark("agent_0", max_retries=1)
        shark.initialize_session = AsyncMock()
        shark.session = MagicMock()
        shark.session.id = "ses_123"
        
        with patch.object(Shark, 'chat_robust') as mock_chat:
            # Provide consistently bad responses that trigger LLMResponseError
            mock_chat.return_value = "I am not a JSON object, I am a teapot."
            
            state = MarketState(round_num=1, liquidity_b=100.0)
            
            # EXPECTATION: It should NOT raise FatalAgentError, but return empty AgentAction
            action = await shark.get_action(state)
            
            self.assertIsInstance(action, AgentAction)
            self.assertEqual(action.agent_id, "agent_0")
            self.assertEqual(action.beliefs, {})
            # Verify it attempted multiple times before giving up
            self.assertGreaterEqual(mock_chat.call_count, 3)

    @patch('market.agents.shark.AsyncOpencode')
    async def test_get_action_scaling_timeout_verification(self, MockClient):
        # Verify that timeout doubles on each retry
        shark = Shark("agent_0", max_retries=2, timeout=10.0, max_backoff=100.0)
        shark.initialize_session = AsyncMock()
        shark.session = MagicMock()
        shark.session.id = "ses_123"
        shark.interrupt = AsyncMock()
        
        with patch.object(Shark, 'chat_robust') as mock_chat:
            mock_chat.side_effect = [
                APITimeoutError("Timeout 1"),
                APITimeoutError("Timeout 2"),
                '{"beliefs": {"cand_0": 1.0}}' # Succeed on 3rd attempt
            ]
            
            state = MarketState(round_num=1, liquidity_b=100.0)
            action = await shark.get_action(state)
            
            self.assertEqual(action.beliefs["cand_0"], 1.0)
            self.assertEqual(mock_chat.call_count, 3)
            
            # Verify timeout scaling: 10, 20, 40
            calls = mock_chat.call_args_list
            self.assertEqual(calls[0].kwargs.get("timeout"), 10.0)
            self.assertEqual(calls[1].kwargs.get("timeout"), 20.0)
            self.assertEqual(calls[2].kwargs.get("timeout"), 40.0)

if __name__ == "__main__":
    unittest.main()
