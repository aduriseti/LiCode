import unittest
from collections import deque
from unittest import mock

from opencode_ai.types import TextPart
from opencode_ai.types.event_list_response import EventMessagePartUpdated

from market.agents.shark import Shark
from market.core.state import MarketState


class TestPromptRetention(unittest.IsolatedAsyncioTestCase):
    @mock.patch("market.agents.shark.AsyncOpencode")
    async def test_error_propagation_on_parsing_failure(self, MockClient):
        """Verifies that an error message is sent back to the agent on parsing failure."""
        shark = Shark("agent_0")
        state = MarketState(round_num=1, liquidity_b=100.0, prompt="test")

        shark.initialize_session = mock.AsyncMock()
        shark.session = mock.MagicMock()
        shark.session.id = "ses_123"

        # 1. Setup Mock Client with recovery responses
        client_inst = MockClient.return_value
        shark.client = client_inst  # Ensure shark uses the same mock client

        def create_mock_stream(content_text):
            mock_event = mock.MagicMock(spec=EventMessagePartUpdated)
            mock_event.properties = mock.MagicMock()
            mock_part = mock.MagicMock(spec=TextPart)
            mock_part.text = content_text
            mock_part.session_id = "ses_123"
            mock_part.id = "p1"
            mock_event.properties.part = mock_part

            async def mock_iter():
                yield mock_event

            mock_stream = mock.MagicMock()
            mock_stream.close = mock.AsyncMock()
            mock_stream.__aiter__.side_effect = lambda: mock_iter()
            return mock_stream

        client_inst.event.list = mock.AsyncMock(return_value=create_mock_stream(""))
        client_inst.close = mock.AsyncMock()
        client_inst.session.chat = mock.AsyncMock()

        contents = ["I am not JSON", '{"beliefs": {"cand_0": 0.5}, "proposals": []}']
        msg_contents = deque(contents)

        async def messages_side_effect(*args, **kwargs):
            c = msg_contents.popleft() if msg_contents else contents[-1]
            mock_part = mock.MagicMock(spec=TextPart)
            mock_part.text = c
            mock_msg = mock.MagicMock()
            mock_msg.parts = [mock_part]
            return [mock_msg]

        client_inst.session.messages = mock.AsyncMock(side_effect=messages_side_effect)

        action = await shark.get_action(state)

        # Verify
        self.assertEqual(client_inst.session.chat.call_count, 2)

        # Check arguments of the second call
        args, kwargs = client_inst.session.chat.call_args_list[1]
        sent_prompt = kwargs["parts"][0]["text"]

        self.assertIn("ERROR:", sent_prompt, "Second attempt should be an error message")
        self.assertIn("invalid", sent_prompt)
        self.assertNotIn(
            "PROBLEM STATEMENT",
            sent_prompt,
            "Second attempt should NOT contain the full state prompt",
        )


if __name__ == "__main__":
    unittest.main()
