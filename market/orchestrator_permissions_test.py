import unittest
import os
import shutil
import stat
import tempfile
from market.orchestrator import Orchestrator, AgentAction

class PermissionsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orch = Orchestrator("Test Perms", n_agents=1, base_dir=self.test_dir)
        await self.orch.initialize()

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir)

    def test_candidate_dir_permissions(self):
        # Check cand_0 directory
        cand_dir = os.path.join(self.test_dir, "worktrees", "cand_0")
        self.assertTrue(os.path.exists(cand_dir))
        
        mode = os.stat(cand_dir).st_mode
        # Check for 755 (rwxr-xr-x)
        # S_IRWXU | S_IRGRP | S_IXGRP | S_IROTH | S_IXOTH
        expected = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
        self.assertEqual(mode & 0o777, 0o755)
        
        # Check a file that definitely exists in the repo (e.g. market/cli.py)
        # The orchestrator clones the CWD into cand_0
        sol_path = os.path.join(cand_dir, "market", "cli.py")
        if os.path.exists(sol_path):
            mode_file = os.stat(sol_path).st_mode
            self.assertEqual(mode_file & 0o777, 0o644)

    async def test_verifier_dir_permissions(self):
        # Create a verifier proposal
        action = AgentAction("agent_0", proposals=[
            {"type": "VERIFIER", "code": "print('ok')"}
        ])
        await self.orch.process_round([action])
        
        # Find the verifier dir
        v_base = os.path.join(self.test_dir, "verifiers")
        v_dirs = os.listdir(v_base)
        self.assertTrue(len(v_dirs) > 0)
        
        v_path = os.path.join(v_base, v_dirs[0])
        mode = os.stat(v_path).st_mode
        self.assertEqual(mode & 0o777, 0o755)
        
        # Check run.sh (755) and verify it is executable
        run_sh = os.path.join(v_path, "run.sh")
        mode_sh = os.stat(run_sh).st_mode
        self.assertEqual(mode_sh & 0o777, 0o755)
        self.assertTrue(bool(mode_sh & stat.S_IXUSR))
        self.assertTrue(bool(mode_sh & stat.S_IXGRP))
        self.assertTrue(bool(mode_sh & stat.S_IXOTH))
        
        # Check test.py (644) and verify it is readable
        test_py = os.path.join(v_path, "test.py")
        mode_py = os.stat(test_py).st_mode
        self.assertEqual(mode_py & 0o777, 0o644)
        self.assertTrue(os.access(test_py, os.R_OK))

if __name__ == '__main__':
    unittest.main()
