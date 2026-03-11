import unittest
from unittest import mock
import os
import subprocess
from market.orchestrator import Orchestrator
from market.core.state import MarketState, MarketAsset, AgentPortfolio

class OrchestratorRobustnessTest(unittest.IsolatedAsyncioTestCase):
    """
    Tests for Orchestrator resilience: handling non-UTF-8 characters in reports.
    """

    @mock.patch('market.orchestrator.subprocess.run')
    @mock.patch('market.orchestrator.os.path.isdir')
    @mock.patch('market.orchestrator.open', new_callable=mock.mock_open)
    async def test_get_final_report_with_binary_diff(self, mock_file, mock_isdir, mock_run):
        # 1. Setup
        orch = Orchestrator("Test", n_agents=1, budget=100.0)
        orch.state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path="/tmp/cand_0")
        orch.state.agents["agent_0"] = AgentPortfolio("agent_0", wealth=100.0)
        
        mock_isdir.return_value = True
        
        # 2. Mock git calls
        def run_side_effect(args, **kwargs):
            m = mock.Mock()
            if args == ["git", "log", "--grep=Initial Baseline", "--format=%H", "-n", "1"]:
                m.stdout = "abc123hash"
                m.returncode = 0
            elif args[0:2] == ["git", "diff"]:
                # BINARY DIFF (with non-UTF8 byte 0x90)
                m.stdout = b"""diff --git a/file.bin b/file.bin
@@ -1 +1 @@
Binary content \x90
"""
                m.returncode = 0
            else:
                m.stdout = b""
                m.returncode = 0
            return m
        mock_run.side_effect = run_side_effect
        
        # 3. Call method
        report = orch.get_final_report()
        
        # 4. Verify
        self.assertIn("Tournament Complete", report)
        self.assertIn("Binary content", report)
        # Check for replacement character (U+FFFD)
        self.assertIn("\ufffd", report)

    @mock.patch('market.orchestrator.subprocess.run')
    @mock.patch('market.orchestrator.os.path.isdir')
    @mock.patch('market.orchestrator.os.path.exists')
    async def test_get_final_report_with_binary_fallback(self, mock_exists, mock_isdir, mock_run):
        # 1. Setup
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            cand_path = os.path.join(tmp_dir, "cand_0")
            os.makedirs(cand_path)
            solution_py = os.path.join(cand_path, "solution.py")
            
            # Write invalid UTF-8 bytes
            with open(solution_py, "wb") as f:
                f.write(b"Binary file \x90")
            
            orch = Orchestrator("Test", n_agents=1, budget=100.0)
            orch.state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path=cand_path)
            orch.state.agents["agent_0"] = AgentPortfolio("agent_0", wealth=100.0)
            
            mock_isdir.return_value = True
            mock_exists.return_value = True # for solution.py
            
            # 2. Mock git calls (empty diff)
            def run_side_effect(args, **kwargs):
                m = mock.Mock()
                if args == ["git", "log", "--grep=Initial Baseline", "--format=%H", "-n", "1"]:
                    m.stdout = "abc123hash"
                    m.returncode = 0
                elif args[0:2] == ["git", "diff"]:
                    m.stdout = b"" # No changes
                    m.returncode = 0
                else:
                    m.stdout = b""
                    m.returncode = 0
                return m
            mock_run.side_effect = run_side_effect
            
            # 3. Call method
            # We don't mock 'open' here, let it use the real one for solution.py
            # But Orchestrator.get_final_report uses os.path.join(winner.code_path, "solution.py")
            # which we set to cand_path.
            report = orch.get_final_report()
            
            # 4. Verify fallback to solution.py content
            self.assertIn("Full Content of solution.py", report)
            self.assertIn("Binary file", report)
            self.assertIn("\ufffd", report)

if __name__ == "__main__":
    unittest.main()
