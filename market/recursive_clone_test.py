import unittest
import os
import shutil
import asyncio
from market.orchestrator import Orchestrator

class TestRecursiveClone(unittest.IsolatedAsyncioTestCase):
    async def test_arenas_exclusion(self):
        """Verifies that .arenas directory is NOT copied during workspace cloning."""
        # Setup a dummy source environment
        src_dir = os.path.join(os.getcwd(), "test_src_recursive")
        if os.path.exists(src_dir):
            shutil.rmtree(src_dir)
        os.makedirs(src_dir)
        
        # Create a dummy file that should be copied
        with open(os.path.join(src_dir, "keep.txt"), "w") as f:
            f.write("keep me")
            
        # Create a dummy .arenas directory that should NOT be copied
        arenas_dir = os.path.join(src_dir, ".arenas")
        os.makedirs(arenas_dir)
        with open(os.path.join(arenas_dir, "should_not_exist.txt"), "w") as f:
            f.write("i should be excluded")
            
        # Initialize Git in the source directory (needed for _clone_workspace)
        import subprocess
        subprocess.run(["git", "init"], cwd=src_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=src_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=src_dir, check=True, capture_output=True)
        subprocess.run(["git", "add", "keep.txt"], cwd=src_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=src_dir, check=True, capture_output=True)
        
        # Add an untracked file to test the 'ls-files -o' part
        with open(os.path.join(src_dir, "untracked.txt"), "w") as f:
            f.write("untracked but should be copied")

        # Destination directory
        dest_base = os.path.join(os.getcwd(), "test_dest_recursive")
        if os.path.exists(dest_base):
            shutil.rmtree(dest_base)
            
        # We need to run Orchestrator._clone_workspace from the source directory
        # but Orchestrator uses os.getcwd() as source. So we change dir temporarily.
        original_cwd = os.getcwd()
        os.chdir(src_dir)
        
        try:
            orch = Orchestrator("test", 1, budget=100.0, base_dir=dest_base)
            dest_dir = os.path.join(dest_base, "worktrees", "cand_0")
            
            # Execute cloning
            await orch._clone_workspace(dest_dir)
            
            # Assertions
            self.assertTrue(os.path.exists(os.path.join(dest_dir, "keep.txt")), "Tracked file should be copied")
            self.assertTrue(os.path.exists(os.path.join(dest_dir, "untracked.txt")), "Untracked file should be copied")
            self.assertFalse(os.path.exists(os.path.join(dest_dir, ".arenas")), ".arenas directory should be excluded")
            
        finally:
            os.chdir(original_cwd)
            if os.path.exists(src_dir):
                shutil.rmtree(src_dir)
            if os.path.exists(dest_base):
                shutil.rmtree(dest_base)

if __name__ == "__main__":
    unittest.main()
