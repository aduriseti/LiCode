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
    @patch('market.agents.shark.asyncio.create_subprocess_shell') # Mock shell for git add
    @patch('market.agents.shark.asyncio.create_subprocess_exec')
    @patch('market.agents.shark.os.path.isdir') # Changed from exists to isdir
    @patch('market.agents.shark.os.listdir')
    @patch('market.agents.shark.open', new_callable=mock_open)
    async def test_format_state_prompt_content(self, mock_file, mock_listdir, mock_isdir, mock_exec, mock_shell, mock_run):
        # Setup State
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Solve X")
        cand_path = "/tmp/cand_0"
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path=cand_path)
        
        ver_path = "/tmp/v_1"
        state.assets["v_1"] = MarketAsset("v_1", "VERIFIER", "Test V", test_path=ver_path)
        
        shark = Shark("agent_0")
        
        # Mocks
        mock_isdir.return_value = True
        
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

        # Mock 'git add .'
        mock_shell_process = MagicMock()
        mock_shell_process.wait = AsyncMock()
        mock_shell.return_value = mock_shell_process

        # Mock 'git diff'
        mock_process = MagicMock()
        # communicate returns (stdout, stderr)
        mock_process.communicate = AsyncMock(return_value=(
            b"diff --git a/main.py b/main.py\n@@ -1 +1 @@\ndiff output line 1\n+ line 2\n",
            b""
        ))
        mock_process.returncode = 0
        mock_exec.return_value = mock_process
        
        # Call Method
        prompt = await shark._format_state_prompt(state)
        
        # Assertions
        self.assertIn("You are Agent: agent_0", prompt)
        self.assertIn("=== Candidate Code Changes (Diffs) ===", prompt)
        self.assertIn("diff output line 1", prompt)
        self.assertIn("=== Verifier Code ===", prompt)

    @patch('market.agents.shark.asyncio.create_subprocess_shell')
    @patch('market.agents.shark.asyncio.create_subprocess_exec')
    @patch('market.agents.shark.os.path.isdir')
    async def test_format_state_prompt_no_error_on_valid_diff(self, mock_isdir, mock_exec, mock_shell):
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Fix Bug")
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path="/tmp/cand_0")
        
        shark = Shark("agent_0")
        mock_isdir.return_value = True
        
        # Mock git add
        mock_shell.return_value.wait = AsyncMock()

        # Mock successful diff with changes
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(
            b"diff --git a/file.py b/file.py\n@@ -1 +1 @@\nsome diff content\n",
            b""
        ))
        mock_process.returncode = 0
        mock_exec.return_value = mock_process
        
        prompt = await shark._format_state_prompt(state)
        
        self.assertIn("some diff content", prompt)

    @patch('market.agents.shark.asyncio.create_subprocess_shell')
    @patch('market.agents.shark.asyncio.create_subprocess_exec')
    @patch('market.agents.shark.os.path.isdir')
    async def test_format_state_prompt_handles_timeout(self, mock_isdir, mock_exec, mock_shell):
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Fix Bug")
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path="/tmp/cand_0")
        
        shark = Shark("agent_0")
        mock_isdir.return_value = True
        
        mock_shell.return_value.wait = AsyncMock()

        mock_process = MagicMock()
        # Mock an exception during communicate (simulating timeout or crash)
        mock_process.communicate = AsyncMock(side_effect=Exception("Timeout or Crash"))
        mock_exec.return_value = mock_process
        
        prompt = await shark._format_state_prompt(state)
        
        self.assertIn("[Error: Timeout or Crash]", prompt)

    @patch('market.agents.shark.asyncio.create_subprocess_shell')
    @patch('market.agents.shark.asyncio.create_subprocess_exec')
    @patch('market.agents.shark.os.path.isdir')
    async def test_format_state_prompt_no_diff(self, mock_isdir, mock_exec, mock_shell):
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Fix Bug")
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path="/tmp/cand_0")
        
        shark = Shark("agent_0")
        mock_isdir.return_value = True
        
        mock_shell.return_value.wait = AsyncMock()

        # Mock empty diff
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0
        mock_exec.return_value = mock_process
        
        prompt = await shark._format_state_prompt(state)
        
        self.assertIn("--- cand_0 Diff ---", prompt)
        self.assertIn("(No changes from baseline)", prompt)

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
        # We expect fallback Action after all self-correction attempts fail
        async def run_test():
            # Mock the chat method to consistently return non-JSON content
            shark._chat_with_network_retry = AsyncMock(return_value=mock_response.text)
            action = await shark.get_action(state)
            self.assertEqual(action.agent_id, "agent_0")
            self.assertEqual(action.beliefs, {})
            self.assertEqual(action.proposals, [])
    
        loop.run_until_complete(run_test())
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