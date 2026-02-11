import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from market.agents.shark import Shark, LLMResponseError
from market.core.state import MarketState

class TestSharkParsing(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.shark = Shark("agent_0", api_url="http://mock")
        self.shark.session = MagicMock()
        self.shark.session.id = "ses_123"
        self.state = MarketState(round_num=1, liquidity_b=100.0)

    @patch('market.agents.shark.AsyncOpencode')
    async def test_parsing_success_markdown(self, MockClient):
        # Mock successful JSON in markdown
        mock_response = MagicMock()
        mock_response.text = 'Some reasoning... ```json\n{"beliefs": {"cand_0": 0.9}, "proposals": []}\n```'
        self.shark.client.session.chat = AsyncMock(return_value=mock_response)

        action = await self.shark.get_action(self.state)
        self.assertEqual(action.beliefs["cand_0"], 0.9)

    @patch('market.agents.shark.AsyncOpencode')
    async def test_parsing_success_raw(self, MockClient):
        # Mock successful raw JSON
        mock_response = MagicMock()
        mock_response.text = '{"beliefs": {"cand_0": 0.8}, "proposals": []}'
        self.shark.client.session.chat = AsyncMock(return_value=mock_response)

        action = await self.shark.get_action(self.state)
        self.assertEqual(action.beliefs["cand_0"], 0.8)

    @patch('market.agents.shark.AsyncOpencode')
    async def test_parsing_failure_no_json(self, MockClient):
        # Mock blabber with no JSON
        mock_response = MagicMock()
        mock_response.text = 'I am thinking about Fibonacci but I will not give you JSON today.'
        self.shark.client.session.chat = AsyncMock(return_value=mock_response)

        # We expect LLMResponseError (which triggers retry)
        with self.assertRaises(LLMResponseError):
             await self.shark.get_action.__wrapped__(self.shark, self.state)

    @patch('market.agents.shark.AsyncOpencode')
    async def test_parsing_malformed_json_recovery(self, MockClient):
        # Mock malformed JSON that has a valid block inside
        mock_response = MagicMock()
        mock_response.text = 'Here is a list: { "item": 1 } and here is the real answer: {"beliefs": {"cand_0": 0.5}}'
        self.shark.client.session.chat = AsyncMock(return_value=mock_response)

        action = await self.shark.get_action(self.state)
        self.assertEqual(action.beliefs["cand_0"], 0.5)

if __name__ == '__main__':
    unittest.main()