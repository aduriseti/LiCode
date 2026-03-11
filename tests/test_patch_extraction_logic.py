import os
import subprocess
import tempfile
import json
import unittest
from evaluate_swe_bench import get_patch_from_winner

class TestPatchExtraction(unittest.TestCase):
    def test_agent_internal_commits_do_not_break_diff(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # 1. Initialize Git Repo
            subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, check=True)
            
            # 2. Initial commit (Upstream state)
            with open(os.path.join(temp_dir, "existing_file.py"), "w") as f:
                f.write("print('hello')\n")
            subprocess.run(["git", "add", "."], cwd=temp_dir, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=temp_dir, check=True, capture_output=True)
            
            # 3. Initial Baseline commit (LiCode starting state)
            # We add problem.md here too
            with open(os.path.join(temp_dir, "problem.md"), "w") as f:
                f.write("Fix the bug\n")
            subprocess.run(["git", "add", "."], cwd=temp_dir, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial Baseline"], cwd=temp_dir, check=True, capture_output=True)
            
            # 4. Agent adds a NEW file and commits it (Simulating agent saving work)
            agent_file_path = os.path.join(temp_dir, "agent_test.py")
            with open(agent_file_path, "w") as f:
                f.write("print('agent test v1')\n")
            subprocess.run(["git", "add", "."], cwd=temp_dir, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Agent internal commit"], cwd=temp_dir, check=True, capture_output=True)
            
            # 5. Agent MODIFIES that same file (but doesn't commit again)
            with open(agent_file_path, "w") as f:
                f.write("print('agent test v2 - modified')\n")
            
            # 6. Reconstruct state dict for get_patch_from_winner
            state_dict = {
                "round_num": 1,
                "liquidity_b": 100,
                "assets": {
                    "cand_0": {
                        "id": "cand_0",
                        "type": "CANDIDATE",
                        "description": "test",
                        "code_path": temp_dir,
                        "q_yes": 10,
                        "q_no": 5
                    }
                },
                "agents": {},
                "bonds": [],
                "whale_wealth": 1000,
                "whale_shares": {}
            }
            
            # 7. Generate the patch
            patch = get_patch_from_winner(temp_dir, "Tournament Report", state_dict)
            
            # VERIFICATION:
            # The diff should show agent_test.py as a NEW FILE (--- /dev/null)
            # instead of a MODIFICATION against the agent's internal commit.
            
            self.assertIn("--- /dev/null", patch, "Patch should show new file addition using /dev/null")
            self.assertIn("+++ b/agent_test.py", patch, "Patch should include agent_test.py")
            self.assertIn("agent test v2 - modified", patch, "Patch should contain the final content")
            
            # problem.md should be EXCLUDED
            self.assertNotIn("problem.md", patch, "problem.md should be excluded from the patch")
            
            # Verify it's not a modification
            self.assertNotIn("--- a/agent_test.py", patch, "Patch should NOT show agent_test.py as a modification of an existing file")

    def test_polluting_files_are_excluded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # 1. Initialize Git Repo
            subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, check=True)
            
            # 2. Initial commit (Upstream state with a real tracked package.json)
            with open(os.path.join(temp_dir, "package.json"), "w") as f:
                f.write('{"name": "original"}\n')
            subprocess.run(["git", "add", "."], cwd=temp_dir, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=temp_dir, check=True, capture_output=True)
            
            # 3. Initial Baseline commit
            subprocess.run(["git", "commit", "--allow-empty", "-m", "Initial Baseline"], cwd=temp_dir, check=True, capture_output=True)
            
            # 4. Agent creates untracked files and modifies the tracked package.json
            with open(os.path.join(temp_dir, "bun.lock"), "w") as f:
                f.write("bun lock content\n")
            with open(os.path.join(temp_dir, "package-lock.json"), "w") as f:
                f.write("npm lock content\n")
            with open(os.path.join(temp_dir, "package.json"), "w") as f:
                f.write('{"name": "polluted"}\n')
                
            # Agent also creates a valid source file to ensure something is in the diff
            with open(os.path.join(temp_dir, "valid_code.py"), "w") as f:
                f.write("print('valid')\n")
            
            # 5. Reconstruct state dict for get_patch_from_winner
            state_dict = {
                "round_num": 1,
                "liquidity_b": 100,
                "assets": {
                    "cand_0": {
                        "id": "cand_0",
                        "type": "CANDIDATE",
                        "description": "test",
                        "code_path": temp_dir,
                        "q_yes": 10,
                        "q_no": 5
                    }
                },
                "agents": {},
                "bonds": [],
                "whale_wealth": 1000,
                "whale_shares": {}
            }
            
            # 6. Generate the patch
            patch = get_patch_from_winner(temp_dir, "Tournament Report", state_dict)
            
            # VERIFICATION:
            self.assertIsNotNone(patch, "Patch should not be None")
            self.assertIn("valid_code.py", patch, "Valid source files should be included")
            self.assertNotIn("bun.lock", patch, "bun.lock should be excluded")
            self.assertNotIn("package-lock.json", patch, "package-lock.json should be excluded")
            self.assertNotIn("package.json", patch, "package.json modifications should be excluded")

if __name__ == "__main__":
    unittest.main()
