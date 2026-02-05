import unittest
import tempfile
import os
import shutil
from market.orchestrator import Orchestrator

class PatchTest(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orch = Orchestrator("Test Patch", n_agents=1, base_dir=self.test_dir)
        self.cand_path = os.path.join(self.test_dir, "worktrees", "cand_0", "solution.py")
        
        # Setup initial file
        with open(self.cand_path, "w") as f:
            f.write("def foo():\n    return 1\n")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_patch_success(self):
        proposal = {
            "type": "PATCH",
            "old_code": "return 1",
            "new_code": "return 2"
        }
        self.orch._update_candidate_code(self.cand_path, proposal)
        
        with open(self.cand_path, "r") as f:
            content = f.read()
        self.assertEqual(content, "def foo():\n    return 2\n")

    def test_patch_not_found(self):
        proposal = {
            "type": "PATCH",
            "old_code": "return 999",
            "new_code": "return 2"
        }
        self.orch._update_candidate_code(self.cand_path, proposal)
        
        with open(self.cand_path, "r") as f:
            content = f.read()
        self.assertEqual(content, "def foo():\n    return 1\n")

    def test_patch_ambiguous(self):
        # Create file with duplicates
        with open(self.cand_path, "w") as f:
            f.write("print('hi')\nprint('hi')")
            
        proposal = {
            "type": "PATCH",
            "old_code": "print('hi')",
            "new_code": "print('bye')"
        }
        self.orch._update_candidate_code(self.cand_path, proposal)
        
        # Should not change
        with open(self.cand_path, "r") as f:
            content = f.read()
        self.assertEqual(content, "print('hi')\nprint('hi')")

if __name__ == '__main__':
    unittest.main()
