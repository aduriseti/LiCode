import unittest
from unittest.mock import MagicMock, patch, AsyncMock, mock_open
import os
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
    @patch('market.agents.shark.os.listdir')
    @patch('market.agents.shark.os.path.exists')
    @patch('market.agents.shark.os.path.isdir')
    @patch('market.agents.shark.os.path.isfile')
    @patch('builtins.open', new_callable=mock_open)
    def test_format_state_prompt_content(self, mock_file, mock_isfile, mock_isdir, mock_exists, mock_listdir, mock_run):
        # Setup Market State
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Fix Bug")
        
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
            if path == cand_path:
                return ["solution.py", "README.md", ".git"]
            if path == ver_path:
                return ["run.sh", "test.py"]
            return []
        mock_listdir.side_effect = listdir_side_effect

        # Mock File Content
        file_content_map = {
            f"{cand_path}/solution.py": "def solve(): return 42",
            f"{cand_path}/README.md": "# Readme",
            f"{ver_path}/run.sh": "#!/bin/bash",
            f"{ver_path}/test.py": "import unittest"
        }
        
        def open_side_effect(file, mode='r', errors=None):
            # Normalize path (mock keys match exactly for simplicity)
            content = file_content_map.get(str(file), "")
            m = mock_open(read_data=content).return_value
            return m
        
        mock_file.side_effect = open_side_effect

        # Mock Subprocess (Diff)
        mock_run.return_value.stdout = "diff output line 1\n+ line 2"
        
        # Call Method
        prompt = shark._format_state_prompt(state)
        
        # Assertions
        
        # 0. Agent Identity
        self.assertIn("You are Agent: agent_0", prompt)
        self.assertIn('Your assigned candidate solution is "cand_0"', shark.system_prompt)
        
        # 1. Candidate Diff
        self.assertIn("=== Candidate Code Changes (Diffs) ===", prompt)
        self.assertIn("--- cand_0 Diff ---", prompt)
        self.assertIn("diff output line 1", prompt)
        
        # 2. Verifier Content
        self.assertIn("=== Verifier Code ===", prompt)
        self.assertIn("--- v_123 Content ---", prompt)
        self.assertIn("File: run.sh", prompt)
        self.assertIn("#!/bin/bash", prompt)
        
        # 3. Own Workspace Files
        self.assertIn("=== Your Workspace Files ===", prompt)
        # Check that file list is present
        self.assertIn("solution.py", prompt)
        self.assertIn("README.md", prompt)
        
        # Check that hidden files are filtered out
        self.assertNotIn(".git", prompt.split("=== Your Workspace Files ===")[1])
        
        # Check that content is NOT dumped
        self.assertNotIn("--- Content of solution.py ---", prompt)
        self.assertNotIn("def solve(): return 42", prompt)
        self.assertIn("(Content omitted - see diffs above)", prompt)

if __name__ == '__main__':
    unittest.main()