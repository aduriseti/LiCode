import unittest
from unittest.mock import MagicMock, patch, AsyncMock, mock_open
import os
import asyncio
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
        mock_client_instance = MockClient.return_value
        mock_client_instance.session.create = AsyncMock(return_value=mock_session)
        mock_client_instance.session.chat = AsyncMock(return_value=mock_response)
        
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Test Prompt")
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc")
        state.agents["agent_0"] = AgentPortfolio("agent_0", 100.0)
        
        shark = Shark("agent_0")
        action = await shark.get_action(state)
        
        self.assertEqual(action.agent_id, "agent_0")
        # Ensure beliefs are parsed correctly
        self.assertIn("cand_0", action.beliefs)
        self.assertEqual(action.beliefs["cand_0"], 0.9)

    @patch('market.agents.shark.subprocess.run')
    @patch('market.agents.shark.asyncio.create_subprocess_shell')
    @patch('market.agents.shark.os.listdir')
    @patch('market.agents.shark.os.path.exists')
    @patch('market.agents.shark.os.path.isdir')
    @patch('market.agents.shark.os.path.isfile')
    @patch('builtins.open', new_callable=mock_open)
    async def test_format_state_prompt_content(self, mock_file, mock_isfile, mock_isdir, mock_exists, mock_listdir, mock_exec, mock_run):
        # Setup Market State
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Fix Bug")
        
        # Mock git ls-files
        mock_run.return_value.stdout = "solution.py"
        
        # Asset 1: Candidate (Folder)
        cand_path = "/tmp/cand_0"
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path=cand_path)
        
        # Asset 2: Verifier (Folder)
        ver_path = "/tmp/v_123"
        state.assets["v_123"] = MarketAsset("v_123", "VERIFIER", "Desc", test_path=ver_path)
        
        # Agent owns cand_0
        shark = Shark("agent_0")
        
        # Mock File System
        mock_exists.return_value = True
        mock_isdir.side_effect = lambda p: p in [cand_path, ver_path]
        mock_isfile.return_value = True
        
        # Mock Directory Listing
        def listdir_side_effect(path):
            if path == cand_path: return ["solution.py", "README.md", ".git"]
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
        mock_process.communicate = AsyncMock(return_value=(b"@@ -1 +1 @@\ndiff output line 1\n+ line 2", b""))
        mock_process.wait = AsyncMock()
        mock_exec.return_value = mock_process
        
        # Call Method
        prompt = await shark._format_state_prompt(state)
        
        # Assertions
        self.assertIn("You are Agent: agent_0", prompt)
        self.assertIn("=== Candidate Code Changes (Diffs) ===", prompt)
        self.assertIn("diff output line 1", prompt)
        self.assertIn("=== Verifier Code ===", prompt)
        self.assertNotIn("=== Your Workspace Files ===", prompt)

    @patch('market.agents.shark.subprocess.run')
    @patch('market.agents.shark.asyncio.create_subprocess_shell')
    @patch('market.agents.shark.os.path.exists')
    async def test_format_state_prompt_no_error_on_valid_diff(self, mock_exists, mock_exec, mock_run):
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Fix Bug")
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path="/tmp/cand_0")
        
        shark = Shark("agent_0")
        mock_exists.return_value = True
        mock_run.return_value.stdout = "solution.py"
        
        # Mock successful diff with changes
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"@@ -1 +1 @@\nsome diff content", b""))
        mock_process.wait = AsyncMock()
        mock_exec.return_value = mock_process
        
        with patch('market.agents.shark.os.path.isfile', return_value=True):
            prompt = await shark._format_state_prompt(state)
        
        self.assertNotIn("[Error generating diff", prompt)
        self.assertIn("some diff content", prompt)

    @patch('market.agents.shark.subprocess.run')
    @patch('market.agents.shark.asyncio.create_subprocess_shell')
    @patch('market.agents.shark.os.path.exists')
    async def test_format_state_prompt_handles_timeout(self, mock_exists, mock_exec, mock_run):
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Fix Bug")
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path="/tmp/cand_0")
        
        shark = Shark("agent_0")
        mock_exists.return_value = True
        mock_run.return_value.stdout = "solution.py"
        
        mock_process = MagicMock()
        mock_process.communicate.return_value = asyncio.Future()
        mock_process.wait = AsyncMock()
        mock_exec.return_value = mock_process
        
        orig_wait_for = asyncio.wait_for
        async def mock_wait_for(aw, timeout):
            if timeout == 5: raise asyncio.TimeoutError()
            return await orig_wait_for(aw, timeout)

        with patch('market.agents.shark.asyncio.wait_for', side_effect=mock_wait_for):
            with patch('market.agents.shark.os.path.isfile', return_value=True):
                prompt = await shark._format_state_prompt(state)
        
        self.assertIn("[Error generating diff for solution.py", prompt)

    @patch('market.agents.shark.subprocess.run')
    @patch('market.agents.shark.asyncio.create_subprocess_shell')
    @patch('market.agents.shark.os.path.exists')
    async def test_format_state_prompt_no_diff(self, mock_exists, mock_exec, mock_run):
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Fix Bug")
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path="/tmp/cand_0")
        
        shark = Shark("agent_0")
        mock_exists.return_value = True
        mock_run.return_value.stdout = "solution.py"
        
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.wait = AsyncMock()
        mock_exec.return_value = mock_process
        
        with patch('market.agents.shark.os.path.isfile', return_value=True):
            prompt = await shark._format_state_prompt(state)
        
        self.assertIn("--- cand_0 Diff ---", prompt)
        self.assertIn("(Candidate exactly matches base project - no changes made yet)", prompt)
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Fix Bug")
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path="/tmp/cand_0")
        
        shark = Shark("agent_0")
        mock_exists.return_value = True
        
        # Mock git ls-files to return solution.py
        mock_run.return_value.stdout = "solution.py"
        
        # Mock empty diff
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.wait = AsyncMock()
        mock_process.returncode = 0
        mock_exec.return_value = mock_process
        
        # Mock isfile to return True so it attempts the diff
        with patch('market.agents.shark.os.path.isfile', return_value=True):
            prompt = await shark._format_state_prompt(state)
        
        self.assertIn("--- cand_0 Diff ---", prompt)
        self.assertIn("(Candidate exactly matches base project - no changes made yet)", prompt)

if __name__ == '__main__':
    unittest.main()