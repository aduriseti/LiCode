import unittest
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

from market.orchestrator import Orchestrator
from market.core.state import MarketState, AgentPortfolio

class TestOrchestratorVerifier(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orchestrator = Orchestrator(
            prompt="test prompt",
            n_agents=1,
            base_dir=self.test_dir
        )
        # Setup one agent for bond logic
        self.orchestrator.state.agents["agent_0"] = AgentPortfolio(agent_id="agent_0", wealth=100.0)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_create_verifier_with_code_legacy(self):
        """Test backward compatibility with 'code' field."""
        proposal = {"type": "VERIFIER", "code": "print('hello')"}
        vid = self.orchestrator._create_verifier("agent_0", proposal)
        
        self.assertIsNotNone(vid)
        v_path = os.path.join(self.orchestrator.verifiers_dir, vid)
        self.assertTrue(os.path.exists(os.path.join(v_path, "run.sh")))
        self.assertTrue(os.path.exists(os.path.join(v_path, "test.py")))
        
        with open(os.path.join(v_path, "run.sh"), "r") as f:
            content = f.read()
            self.assertTrue(content.startswith("#!/bin/bash"))

    def test_create_verifier_with_files(self):
        """Test new 'files' structure and automatic shebang."""
        proposal = {
            "type": "VERIFIER",
            "files": {
                "run.sh": "python3 main.py",
                "main.py": "import solution"
            }
        }
        vid = self.orchestrator._create_verifier("agent_0", proposal)
        
        self.assertIsNotNone(vid)
        v_path = os.path.join(self.orchestrator.verifiers_dir, vid)
        
        # Verify run.sh has shebang prepended
        with open(os.path.join(v_path, "run.sh"), "r") as f:
            content = f.read()
            self.assertEqual(content, "#!/bin/bash\npython3 main.py")
            
        # Verify main.py exists
        self.assertTrue(os.path.exists(os.path.join(v_path, "main.py")))

    def test_create_verifier_missing_run_sh(self):
        """Test that missing run.sh returns None but doesn't crash."""
        proposal = {
            "type": "VERIFIER",
            "files": {
                "test.py": "print('fail')"
            }
        }
        # Should not raise FileNotFoundError or crash
        vid = self.orchestrator._create_verifier("agent_0", proposal)
        self.assertIsNone(vid)

    def test_create_verifier_traversal_protection(self):
        """Test that directory traversal in filenames is ignored."""
        proposal = {
            "type": "VERIFIER",
            "files": {
                "run.sh": "ls",
                "../evil.sh": "rm -rf /"
            }
        }
        vid = self.orchestrator._create_verifier("agent_0", proposal)
        v_path = os.path.join(self.orchestrator.verifiers_dir, vid)
        
        # run.sh should exist, evil.sh should NOT
        self.assertTrue(os.path.exists(os.path.join(v_path, "run.sh")))
        self.assertFalse(os.path.exists(os.path.join(v_path, "../evil.sh")))
        self.assertFalse(os.path.exists(os.path.join(v_path, "evil.sh")))

if __name__ == '__main__':
    unittest.main()
