import unittest
import os
import shutil
import asyncio
import subprocess
from market.common.workspace import WorkspaceManager

class WorkspaceRegressionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = "/tmp/test_workspace_pollution"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)
        
        # Create a dummy project root (Source)
        self.project_root = os.path.join(self.test_dir, "project")
        os.makedirs(self.project_root)
        
        # Initialize Source as a Git Repo
        subprocess.run(["git", "init"], cwd=self.project_root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@local"], cwd=self.project_root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.project_root, check=True, capture_output=True)
        
        with open(os.path.join(self.project_root, "README.md"), "w") as f:
            f.write("# Test Project\n")
        subprocess.run(["git", "add", "README.md"], cwd=self.project_root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial Commit"], cwd=self.project_root, check=True, capture_output=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    async def test_pending_changes_do_not_pollute_cloned_workspace(self):
        """
        Verifies that pending changes in the source directory are committed in the 
        cloned workspace and do not appear as diffs immediately after cloning.
        """
        # 1. Create a pending change in source
        polluted_file = os.path.join(self.project_root, "README.md")
        with open(polluted_file, "a") as f:
            f.write("Pollution line\n")
            
        # 2. Clone the workspace
        mgr = WorkspaceManager()
        dest_dir = os.path.join(self.test_dir, "cloned_workspace")
        
        await mgr.clone_workspace(self.project_root, dest_dir)
        
        # 3. Verify that get_diff is empty IMMEDIATELY after clone
        diff = mgr.get_diff(dest_dir)
        
        # 4. Check commit log
        log = subprocess.run(["git", "log", "--oneline"], cwd=dest_dir, capture_output=True, text=True).stdout
        print(f"Commit Log:\n{log}")
        
        self.assertIn("Initial Baseline", log, "Initial Baseline commit is missing!")
        self.assertEqual(diff.strip(), "", f"Workspace is polluted with diff:\n{diff}")
        
        # 4. Double check that the pollution IS in the file (it was overlaid and committed)
        with open(os.path.join(dest_dir, "README.md"), "r") as f:
            content = f.read()
            self.assertIn("Pollution line", content, "Pollution line should be present in the file (committed)")

if __name__ == "__main__":
    unittest.main()
