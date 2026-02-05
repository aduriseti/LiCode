import unittest
from unittest.mock import MagicMock, patch
from market.agents.shark import Shark
from market.core.state import MarketState, MarketAsset, AgentPortfolio

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from market.agents.shark import Shark
from market.core.state import MarketState, MarketAsset, AgentPortfolio

class SharkTest(unittest.IsolatedAsyncioTestCase):
    
    @patch('market.agents.shark.AsyncOpencode')
    async def test_get_action_success(self, MockClient):
        # Setup Mock API
        mock_response = MagicMock()
        mock_response.text = '{"beliefs": {"cand_0": 0.9}, "proposals": []}'
        
        mock_session = MagicMock()
        mock_session.id = "ses_123"
        
        # Async methods use AsyncMock
        MockClient.return_value.session.create = AsyncMock(return_value=mock_session)
        MockClient.return_value.session.chat = AsyncMock(return_value=mock_response)
        
        state = MarketState(round_num=1, liquidity_b=10.0)
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc")
        state.agents["agent_0"] = AgentPortfolio("agent_0", 100.0)
        
        shark = Shark("agent_0")
        action = await shark.get_action(state)
        
        self.assertEqual(action.agent_id, "agent_0")
        self.assertEqual(action.beliefs["cand_0"], 0.9)
        
    @patch('market.agents.shark.AsyncOpencode')
    async def test_get_action_failure(self, MockClient):
        # Mock session creation first
        mock_session = MagicMock()
        mock_session.id = "ses_123"
        MockClient.return_value.session.create = AsyncMock(return_value=mock_session)
        
        # API raises error on chat
        MockClient.return_value.session.chat = AsyncMock(side_effect=Exception("API Down"))
        
        state = MarketState(round_num=1, liquidity_b=10.0)
        shark = Shark("agent_0")
        
        # In the real code, we removed the try-except, so it should raise
        with self.assertRaises(Exception):
            await shark.get_action(state)

if __name__ == '__main__':
    unittest.main()

if __name__ == '__main__':
    unittest.main()
