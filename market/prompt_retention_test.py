import unittest
from unittest import mock
import asyncio
from collections import deque
from market.agents.shark import Shark, LLMResponseError
from market.core.state import MarketState
from opencode_ai.types.event_list_response import EventMessagePartUpdated
from opencode_ai.types import TextPart

class TestPromptRetention(unittest.IsolatedAsyncioTestCase):
    @mock.patch('market.agents.shark.AsyncOpencode')
    async def test_error_propagation_on_parsing_failure(self, MockClient):
        """Verifies that an error message is sent back to the agent on parsing failure."""
        shark = Shark("agent_0")
        state = MarketState(round_num=1, liquidity_b=100.0, prompt="test")
        
        shark.initialize_session = mock.AsyncMock()
        shark.session = mock.MagicMock()
        shark.session.id = "ses_123"
        
        # 1. Setup Mock Client with recovery responses
        client_inst = MockClient.return_value
        shark.client = client_inst # Ensure shark uses the same mock client
        
        contents = ["I am not JSON", '{"beliefs": {"cand_0": 0.5}, "proposals": []}']
        msg_contents = deque(contents)

        def create_mock_stream():
            current_content = msg_contents.popleft() if msg_contents else contents[-1]
            
            mock_event = mock.MagicMock(spec=EventMessagePartUpdated)
            mock_event.properties = mock.MagicMock()
            mock_part = mock.MagicMock(spec=TextPart)
            mock_part.text = current_content
            mock_part.session_id = "ses_123"
            mock_part.id = "p1"
            mock_event.properties.part = mock_part
            
            async def mock_iter():
                yield mock_event
                
            mock_stream = mock.MagicMock()
            mock_stream.close = mock.AsyncMock()
            mock_stream.__aiter__.side_effect = lambda: mock_iter()
            return mock_stream

        # chat_robust calls event.list() before session.chat()
        client_inst.event.list = mock.AsyncMock(side_effect=create_mock_stream)
        client_inst.close = mock.AsyncMock()
        
        async def mock_chat(*args, **kwargs):
            # We don't strictly need to return parts since chat_robust prefers stream
            mock_resp = mock.MagicMock()
            mock_resp.parts = []
            return mock_resp

        client_inst.session.chat = mock.AsyncMock(side_effect=mock_chat)
        
        action = await shark.get_action(state)
        
        # Verify
        self.assertEqual(client_inst.session.chat.call_count, 2)
        
        # Check arguments of the second call
        args, kwargs = client_inst.session.chat.call_args_list[1]
        sent_prompt = kwargs['parts'][0]['text']
        
        self.assertIn("ERROR:", sent_prompt, "Second attempt should be an error message")
        self.assertIn("invalid", sent_prompt)
        self.assertNotIn("PROBLEM STATEMENT", sent_prompt, "Second attempt should NOT contain the full state prompt")

if __name__ == "__main__":
    unittest.main()
