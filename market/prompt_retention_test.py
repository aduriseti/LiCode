import unittest
from unittest import mock
import asyncio
from market.agents.shark import Shark, LLMResponseError
from market.core.state import MarketState

class TestPromptRetention(unittest.IsolatedAsyncioTestCase):
    async def test_error_propagation_on_parsing_failure(self):
        """Verifies that an error message is sent back to the agent on parsing failure."""
        shark = Shark("agent_0")
        state = MarketState(round_num=1, liquidity_b=100.0, prompt="test")
        
        shark.initialize_session = mock.AsyncMock()
        shark.session = mock.MagicMock()
        shark.session.id = "ses_123"
        
        # 1. First call: returns garbage
        mock_response_fail = mock.MagicMock()
        mock_response_fail.text = "I am not JSON"
        
        # 2. Second call: returns success
        mock_response_success = mock.MagicMock()
        mock_response_success.text = '{"beliefs": {"cand_0": 0.5}, "proposals": []}'
        
        shark.client.session.chat = mock.AsyncMock(side_effect=[
            mock_response_fail,
            mock_response_success
        ])
        
        action = await shark.get_action(state)
        
        # Verify
        self.assertEqual(shark.client.session.chat.call_count, 2)
        
        # Check arguments of the second call
        args, kwargs = shark.client.session.chat.call_args_list[1]
        sent_prompt = kwargs['parts'][0]['text']
        
        self.assertIn("ERROR:", sent_prompt, "Second attempt should be an error message")
        self.assertIn("invalid", sent_prompt)
        self.assertNotIn("PROBLEM STATEMENT", sent_prompt, "Second attempt should NOT contain the full state prompt")

if __name__ == "__main__":
    unittest.main()
