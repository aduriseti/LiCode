import unittest
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
import asyncio
import os
import io
import json
from market.agents.shark import Shark, LLMResponseError
from market.core.state import MarketState, MarketAsset, AgentPortfolio

class SharkTest(unittest.IsolatedAsyncioTestCase):

    @patch('market.agents.shark.subprocess.run')
    @patch('market.agents.shark.asyncio.create_subprocess_exec')
    @patch('market.agents.shark.os.path.exists')
    @patch('market.agents.shark.os.listdir')
    @patch('market.agents.shark.open', new_callable=mock_open)
    async def test_format_state_prompt_content(self, mock_file, mock_listdir, mock_exists, mock_exec, mock_run):
        # Setup State
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Solve X")
        cand_path = "/tmp/cand_0"
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path=cand_path)
        
        ver_path = "/tmp/v_1"
        state.assets["v_1"] = MarketAsset("v_1", "VERIFIER", "Test V", test_path=ver_path)
        
        shark = Shark("agent_0")
        
        # Mocks
        mock_exists.return_value = True
        
        # Mock Verifier Files
        def listdir_side_effect(path):
            if path == ver_path: return ["run.sh", "test.py"]
            return []
        mock_listdir.side_effect = listdir_side_effect

        # Mock File Content
        file_content_map = {
            f"{ver_path}/run.sh": "#!/bin/bash",
            f"{ver_path}/test.py": "import unittest"
        }
        def open_mock(file, *args, **kwargs):
            return mock_open(read_data=file_content_map.get(str(file), "")).return_value
        mock_file.side_effect = open_mock

        # Mock Subprocess (Diff)
        mock_process = MagicMock()
        mock_stream = MagicMock()
        mock_stream.readline = AsyncMock(side_effect=[
            b"diff -urN ./main.py /tmp/cand_0/main.py\n", 
            b"@@ -1 +1 @@\n",
            b"diff output line 1\n",
            b"+ line 2\n", 
            b""
        ])
        mock_process.stdout = mock_stream
        mock_process.wait = AsyncMock()
        mock_exec.return_value = mock_process
        
        # Call Method
        prompt = await shark._format_state_prompt(state)
        
        # Assertions
        self.assertIn("You are Agent: agent_0", prompt)
        self.assertIn("=== Candidate Code Changes (Diffs) ===", prompt)
        self.assertIn("diff output line 1", prompt)
        self.assertIn("=== Verifier Code ===", prompt)

    @patch('market.agents.shark.subprocess.run')
    @patch('market.agents.shark.asyncio.create_subprocess_exec')
    @patch('market.agents.shark.os.path.exists')
    async def test_format_state_prompt_no_error_on_valid_diff(self, mock_exists, mock_exec, mock_run):
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Fix Bug")
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path="/tmp/cand_0")
        
        shark = Shark("agent_0")
        mock_exists.return_value = True
        
        # Mock successful diff with changes
        mock_process = MagicMock()
        mock_stream = MagicMock()
        mock_stream.readline = AsyncMock(side_effect=[b"diff -urN file.py\n", b"@@ -1 +1 @@\nsome diff content\n", b""])
        mock_process.stdout = mock_stream
        mock_process.wait = AsyncMock()
        mock_exec.return_value = mock_process
        
        with patch('market.agents.shark.os.path.isfile', return_value=True):
            prompt = await shark._format_state_prompt(state)
        
        self.assertIn("some diff content", prompt)

    @patch('market.agents.shark.subprocess.run')
    @patch('market.agents.shark.asyncio.create_subprocess_exec')
    @patch('market.agents.shark.os.path.exists')
    async def test_format_state_prompt_handles_timeout(self, mock_exists, mock_exec, mock_run):
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Fix Bug")
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path="/tmp/cand_0")
        
        shark = Shark("agent_0")
        mock_exists.return_value = True
        
        mock_process = MagicMock()
        mock_process.stdout = MagicMock()
        # Mock a timeout in readline (using a real timeout or exception)
        mock_process.stdout.readline = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.wait = AsyncMock()
        mock_exec.return_value = mock_process
        
        with patch('market.agents.shark.os.path.isfile', return_value=True):
            prompt = await shark._format_state_prompt(state)
        
        self.assertIn("[Error generating diff", prompt)

    @patch('market.agents.shark.subprocess.run')
    @patch('market.agents.shark.asyncio.create_subprocess_exec')
    @patch('market.agents.shark.os.path.exists')
    async def test_format_state_prompt_no_diff(self, mock_exists, mock_exec, mock_run):
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Fix Bug")
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path="/tmp/cand_0")
        
        shark = Shark("agent_0")
        mock_exists.return_value = True
        
        # Mock empty diff
        mock_process = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.wait = AsyncMock()
        mock_exec.return_value = mock_process
        
        with patch('market.agents.shark.os.path.isfile', return_value=True):
            prompt = await shark._format_state_prompt(state)
        
        self.assertIn("--- cand_0 Diff ---", prompt)
        self.assertIn("(Candidate exactly matches base project - no changes made yet)", prompt)

class TestSharkActionParsing(unittest.TestCase):

    @patch('market.agents.shark.AsyncOpencode')
    def test_parsing_success_markdown(self, MockClient):
        # Mock successful JSON in markdown
        mock_response = MagicMock()
        mock_response.text = 'Some reasoning... ```json\n{"beliefs": {"cand_0": 0.9}, "proposals": []}\n```'
        
        mock_session = MagicMock()
        mock_session.id = "ses_123"
        
        mock_client_instance = MockClient.return_value
        mock_client_instance.session.create = AsyncMock(return_value=mock_session)
        mock_client_instance.session.chat = AsyncMock(return_value=mock_response)

        state = MarketState(round_num=1, liquidity_b=100.0)
        shark = Shark("agent_0")
        
        # Use run_until_complete for async in sync test
        loop = asyncio.new_event_loop()
        action = loop.run_until_complete(shark.get_action(state))
        loop.close()
        self.assertEqual(action.beliefs["cand_0"], 0.9)

    @patch('market.agents.shark.AsyncOpencode')
    def test_parsing_success_raw(self, MockClient):
        # Mock successful raw JSON
        mock_response = MagicMock()
        mock_response.text = '{"beliefs": {"cand_0": 0.8}, "proposals": []}'
        
        mock_session = MagicMock()
        mock_session.id = "ses_123"
        
        mock_client_instance = MockClient.return_value
        mock_client_instance.session.create = AsyncMock(return_value=mock_session)
        mock_client_instance.session.chat = AsyncMock(return_value=mock_response)

        state = MarketState(round_num=1, liquidity_b=100.0)
        shark = Shark("agent_0")
        
        loop = asyncio.new_event_loop()
        action = loop.run_until_complete(shark.get_action(state))
        loop.close()
        self.assertEqual(action.beliefs["cand_0"], 0.8)

    @patch('market.agents.shark.AsyncOpencode')
    def test_parsing_failure_no_json(self, MockClient):
        # Mock blabber with no JSON
        mock_response = MagicMock()
        mock_response.text = 'I am thinking about Fibonacci but I will not give you JSON today.'
        
        mock_session = MagicMock()
        mock_session.id = "ses_123"
        
        mock_client_instance = MockClient.return_value
        mock_client_instance.session.create = AsyncMock(return_value=mock_session)
        mock_client_instance.session.chat = AsyncMock(return_value=mock_response)

        state = MarketState(round_num=1, liquidity_b=100.0)
        shark = Shark("agent_0")
        
        loop = asyncio.new_event_loop()
        # We expect LLMResponseError (which triggers retry)
        with self.assertRaises(LLMResponseError):
             loop.run_until_complete(shark.get_action.__wrapped__(shark, state))
        loop.close()

    @patch('market.agents.shark.AsyncOpencode')
    def test_parsing_malformed_json_recovery(self, MockClient):
        # Mock malformed JSON that has a valid block inside
        mock_response = MagicMock()
        mock_response.text = 'Here is a list: { "item": 1 } and here is the real answer: {"beliefs": {"cand_0": 0.5}}'
        
        mock_session = MagicMock()
        mock_session.id = "ses_123"
        
        mock_client_instance = MockClient.return_value
        mock_client_instance.session.create = AsyncMock(return_value=mock_session)
        mock_client_instance.session.chat = AsyncMock(return_value=mock_response)

        state = MarketState(round_num=1, liquidity_b=100.0)
        shark = Shark("agent_0")
        
        loop = asyncio.new_event_loop()
        action = loop.run_until_complete(shark.get_action(state))
        loop.close()
        self.assertEqual(action.beliefs["cand_0"], 0.5)
