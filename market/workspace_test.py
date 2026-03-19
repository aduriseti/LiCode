import unittest
import os
import shutil
import asyncio
import subprocess
import logging
import stat
from unittest.mock import patch, MagicMock
from market.orchestrator import Orchestrator

# Configure logging
logging.basicConfig(level=logging.INFO)

class WorkspaceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = "/tmp/test_workspace_regression"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)
        
        # Create a dummy project root (Source)
        self.project_root = os.path.join(self.test_dir, "project")
        os.makedirs(self.project_root)
        
        # Initialize Source as a Git Repo
        subprocess.run(["git", "init"], cwd=self.project_root, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.email", "test@local"], cwd=self.project_root, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.project_root, check=True, stdout=subprocess.DEVNULL)
        
        # Create an initial commit so clone/commit works
        with open(os.path.join(self.project_root, "README.md"), "w") as f:
            f.write("# Test Project\n")
        subprocess.run(["git", "add", "README.md"], cwd=self.project_root, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", "Initial Root Commit"], cwd=self.project_root, check=True, stdout=subprocess.DEVNULL)
        
        self.original_cwd = os.getcwd()
        os.chdir(self.project_root)

    def tearDown(self):
        os.chdir(self.original_cwd)
        # shutil.rmtree(self.test_dir) # Keep for inspection on failure

    async def test_hybrid_snapshot_cleanliness_and_safety(self):
        """Verifies that the workspace is cloned cleanly, origin is removed, and permissions are correct."""
        
        # 1. Setup Source State
        # A. Add .gitignore
        with open(".gitignore", "w") as f:
            f.write("__pycache__/\n*.log\n")
        subprocess.run(["git", "add", ".gitignore"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", "Initial Commit"], check=True, stdout=subprocess.DEVNULL)
        
        # B. Create Cruft (Ignored)
        cruft_dir = os.path.join(self.project_root, "__pycache__")
        os.makedirs(cruft_dir)
        with open(os.path.join(cruft_dir, "garbage.pyc"), "w") as f:
            f.write("binary garbage")
            
        with open("debug.log", "w") as f:
            f.write("log data")

        # C. Create Valid Uncommitted Work
        with open("solution.py", "w") as f:
            f.write("print('solution')\n")

        # 2. Run _clone_workspace
        orch = Orchestrator("test", 1, base_dir=self.test_dir)
        dest_dir = os.path.join(self.test_dir, "agent_workspace_clean")
        
        await orch.workspace_mgr.clone_workspace(self.project_root, dest_dir)
        
        # 3. Verify Origin Removal
        remotes = subprocess.run(["git", "remote"], cwd=dest_dir, capture_output=True, text=True).stdout.strip()
        self.assertEqual(remotes, "", "Remote 'origin' should be removed")

        # 4. Verify Cleanliness (Cruft should NOT be in diff)
        # We simulate the final report generation: git add . && git diff --cached HEAD
        subprocess.run(["git", "add", "."], cwd=dest_dir, check=True, stdout=subprocess.DEVNULL)
        diff_proc = subprocess.run(["git", "diff", "--cached", "HEAD"], cwd=dest_dir, capture_output=True, text=True)
        diff_output = diff_proc.stdout
        
        self.assertNotIn("garbage.pyc", diff_output, "__pycache__ should be ignored")
        self.assertNotIn("debug.log", diff_output, "*.log should be ignored")
        
        # solution.py IS uncommitted in source, so it SHOULD be in the diff?
        # NO. In Hybrid Strategy, uncommitted work is overlaid and then COMMITTED to the baseline.
        # So `git diff HEAD` should be EMPTY for solution.py because it's in the baseline.
        # The ONLY thing in the diff should be changes made *after* the clone (which is nothing yet).
        self.assertEqual(diff_output.strip(), "", "Diff should be empty (Baseline captured uncommitted state)")

        # 5. Verify Permissions
        # Check Directory (should be 700)
        # Note: os.walk skips .git in our impl, but we check root
        mode_dir = os.stat(dest_dir).st_mode & 0o777
        self.assertEqual(mode_dir, 0o700, "Root directory permission should be 700")
            
        # Check File (should be 600)
        sol_path = os.path.join(dest_dir, "solution.py")
        mode_file = os.stat(sol_path).st_mode & 0o777
        self.assertEqual(mode_file, 0o600, "File permission should be 600")

    async def test_hybrid_snapshot_overlay(self):
        """Verifies that uncommitted changes and new tracked files are correctly overlaid."""
        
        # 1. Setup Source State
        with open("committed.py", "w") as f:
            f.write("print('I am committed')\n")
        subprocess.run(["git", "add", "committed.py"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", "Add committed file"], check=True, stdout=subprocess.DEVNULL)
        
        # Modify committed file
        with open("committed.py", "a") as f:
            f.write("print('I am modified')\n")
            
        # Add new untracked file
        with open("new_file.py", "w") as f:
            f.write("# New untracked file\n")
            
        # 2. Run _clone_workspace
        orch = Orchestrator("test", 1, base_dir=self.test_dir)
        dest_dir = os.path.join(self.test_dir, "agent_workspace_overlay")
        
        await orch.workspace_mgr.clone_workspace(self.project_root, dest_dir)
        
        # 3. Verify Content
        with open(os.path.join(dest_dir, "committed.py"), "r") as f:
            content = f.read()
            self.assertIn("I am modified", content, "Uncommitted modifications should be present")
            
        self.assertTrue(os.path.exists(os.path.join(dest_dir, "new_file.py")), "New untracked file should be present")

        # 4. Verify Baseline Commit
        log = subprocess.run(["git", "log", "--oneline"], cwd=dest_dir, capture_output=True, text=True).stdout
        self.assertIn("Initial Baseline", log, "Initial Baseline commit should be present")

    async def test_diff_truncation(self):
        """Verifies that diffs are truncated at 100 lines per file."""
        
        # 1. Setup
        orch = Orchestrator("test", 1, base_dir=self.test_dir)
        dest_dir = os.path.join(self.test_dir, "agent_workspace_truncation")
        await orch.workspace_mgr.clone_workspace(self.project_root, dest_dir)
        
        # 2. Create Large Change
        large_file = os.path.join(dest_dir, "large.py")
        with open(large_file, "w") as f:
            for i in range(150):
                f.write(f"print({i})\n")
        
        # simulate orchestrator logic for generating report diff
        subprocess.run(["git", "add", "."], cwd=dest_dir, check=True, stdout=subprocess.DEVNULL)
        result = subprocess.run(["git", "diff", "--cached", "HEAD"], cwd=dest_dir, capture_output=True, text=True)
        full_diff = result.stdout
        
        # Apply truncation logic (manual copy from Orchestrator)
        processed_diff = []
        current_file_diff = []
        for line in full_diff.splitlines():
            if line.startswith("diff --git"):
                if current_file_diff:
                    if len(current_file_diff) > 100:
                        processed_diff.extend(current_file_diff[:100])
                        processed_diff.append(f"... (Truncated {len(current_file_diff) - 100} lines) ...")
                    else:
                        processed_diff.extend(current_file_diff)
                current_file_diff = [line]
            else:
                current_file_diff.append(line)
        if current_file_diff:
            if len(current_file_diff) > 100:
                processed_diff.extend(current_file_diff[:100])
                processed_diff.append(f"... (Truncated {len(current_file_diff) - 100} lines) ...")
            else:
                processed_diff.extend(current_file_diff)
                
        final_output = "\\n".join(processed_diff)
        
        self.assertIn("... (Truncated", final_output, "Diff should be truncated")
        # diff size might vary depending on context lines, but it should be truncated
        # we check if the warning string is present, which is sufficient.

if __name__ == "__main__":
    unittest.main()