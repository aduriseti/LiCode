import os
import json
import shutil
import tempfile
import unittest
import asyncio
from unittest import mock
from market.orchestrator import Orchestrator
from market.runner import MarketRunner
from market.agents.shark import Shark
from market.core.state import MarketState, MarketAsset

class TestIsolationRegression(unittest.IsolatedAsyncioTestCase):
    """
    Regression tests for agent isolation and security features.
    Verifies:
    1. Agent worktrees are restricted to 0o700.
    2. baseline.diff is generated for each agent.
    3. OPENCODE_PERMISSION env var is set correctly for agent servers.
    4. Absolute filesystem paths are masked in agent prompts.
    """
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        # Create a dummy git repo to clone from
        self.repo_dir = os.path.join(self.test_dir, "repo")
        os.makedirs(self.repo_dir)
        import subprocess
        subprocess.run(["git", "init"], cwd=self.repo_dir, check=True, capture_output=True)
        
        # Initial commit
        with open(os.path.join(self.repo_dir, "base.txt"), "w") as f:
            f.write("base content")
        subprocess.run(["git", "add", "."], cwd=self.repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.repo_dir, check=True, capture_output=True)
        
        # Add uncommitted changes (to be captured in baseline.diff)
        with open(os.path.join(self.repo_dir, "base.txt"), "a") as f:
            f.write("\nmodified")
        with open(os.path.join(self.repo_dir, "untracked.txt"), "w") as f:
            f.write("new file")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    async def test_orchestrator_isolation_and_context(self):
        """Verifies baseline.diff, 0o700 worktree permissions, and 0o711 parent permissions."""
        base_dir = os.path.join(self.test_dir, "arena")
        orch = Orchestrator("test", 1, base_dir=base_dir)
        
        # Mock os.getcwd to clone from our dummy repo
        with mock.patch("os.getcwd", return_value=self.repo_dir):
            await orch.initialize()
            
            # 0. Verify Parent Permissions (0o711)
            worktrees_dir = os.path.join(base_dir, "worktrees")
            mode_parent = os.stat(worktrees_dir).st_mode & 0o777
            self.assertEqual(mode_parent, 0o711, f"worktrees_dir should be 0o711, got {oct(mode_parent)}")

            dest_dir = os.path.join(base_dir, "worktrees", "cand_0")
            
            # 1. Verify baseline.diff
            diff_path = os.path.join(dest_dir, "baseline.diff")
            self.assertTrue(os.path.exists(diff_path), "baseline.diff should be generated")
            with open(diff_path, "r") as f:
                content = f.read()
                self.assertIn("+modified", content)
                self.assertIn("untracked.txt", content)
            
            # 2. Verify OS-level permissions (0o700)
            mode = os.stat(dest_dir).st_mode & 0o777
            self.assertEqual(mode, 0o700, f"Worktree root should be 0o700, got {oct(mode)}")
            
            # Files should be 0o600
            file_mode = os.stat(os.path.join(dest_dir, "base.txt")).st_mode & 0o777
            self.assertEqual(file_mode, 0o600, f"Worktree files should be 0o600, got {oct(file_mode)}")

    async def test_runner_opencode_permissions(self):
        """Verifies OPENCODE_PERMISSION env var is injected into agent servers."""
        runner = MarketRunner("test", 1, 1000.0)
        
        # Mocking asyncio.create_subprocess_exec to capture environment
        with mock.patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock process lifecycle
            mock_proc = mock.MagicMock()
            mock_proc.returncode = None
            mock_proc.poll.return_value = None
            mock_proc.wait = mock.AsyncMock()
            mock_exec.return_value = mock_proc

            # Mock successful connection check
            async def mock_connect(*args, **kwargs):
                mock_writer = mock.MagicMock()
                mock_writer.wait_closed = mock.AsyncMock()
                return mock.MagicMock(), mock_writer
            
            with mock.patch("asyncio.open_connection", side_effect=mock_connect):
                # Ensure cand_0 dir exists for the runner to find
                cand_dir = os.path.join(runner.arena_dir, "worktrees", "cand_0")
                os.makedirs(cand_dir, exist_ok=True)
                
                # Mock port finding
                runner._find_free_port = mock.MagicMock(return_value=1234)
                
                await runner._start_agent_server("agent_0", 1234)
                
                # Check environment passed to exec
                _, kwargs = mock_exec.call_args
                env = kwargs.get("env", {})
                self.assertIn("OPENCODE_PERMISSION", env)
                self.assertIn("OPENCODE_CONFIG_CONTENT", env)
                self.assertEqual(env.get("DEBUG"), "opencode:provider:*")
                self.assertEqual(env.get("OPENCODE_LOG"), "debug")
                
                # Check permission object
                perms_raw = json.loads(env["OPENCODE_PERMISSION"])
                self.assertEqual(perms_raw["external_directory"], "deny")
                
                # Check log file path in traces directory
                self.assertTrue(runner.traces_dir.endswith("traces"))
                log_path = os.path.join(runner.traces_dir, "cand_0_opencode_serve.log")
                self.assertEqual(kwargs.get("stdout").name, log_path)

    async def test_runner_config_plumbing(self):
        """Verifies model_id and provider_id are injected into agent servers."""
        test_model = "test-model-123"
        test_provider = "test-provider-456"
        runner = MarketRunner("test", 1, 1000.0, model=test_model, provider=test_provider)
        
        with mock.patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = mock.MagicMock()
            mock_proc.returncode = None
            mock_proc.poll.return_value = None
            mock_proc.wait = mock.AsyncMock()
            mock_exec.return_value = mock_proc

            async def mock_connect(*args, **kwargs):
                mock_writer = mock.MagicMock()
                mock_writer.wait_closed = mock.AsyncMock()
                return mock.MagicMock(), mock_writer
            
            with mock.patch("asyncio.open_connection", side_effect=mock_connect):
                cand_dir = os.path.join(runner.arena_dir, "worktrees", "cand_0")
                os.makedirs(cand_dir, exist_ok=True)
                runner._find_free_port = mock.MagicMock(return_value=1234)
                
                await runner._start_agent_server("agent_0", 1234)
                
                _, kwargs = mock_exec.call_args
                env = kwargs.get("env", {})
                self.assertIn("OPENCODE_CONFIG_CONTENT", env)
                
                config = json.loads(env["OPENCODE_CONFIG_CONTENT"])
                self.assertEqual(config["model"], f"{test_provider}/{test_model}")

    async def test_runner_config_validation(self):
        """Verifies that the generated OPENCODE_CONFIG_CONTENT is a valid Config object."""
        from opencode_ai.types import Config
        from pydantic import ConfigDict
        from typing import Optional
        runner = MarketRunner("test", 1, 1000.0, model="gemini", provider="google")
        
        # Define a strict version of Config for testing
        # We explicitly add 'snapshot' because although it's a valid server option,
        # it is currently missing from the official Pydantic models in opencode-ai.
        class StrictConfig(Config):
            model_config = ConfigDict(extra='forbid')
            snapshot: Optional[bool] = None

        with mock.patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock process lifecycle
            mock_proc = mock.MagicMock()
            mock_proc.returncode = None
            mock_proc.poll.return_value = None
            mock_proc.wait = mock.AsyncMock()
            mock_exec.return_value = mock_proc

            # Mock successful connection check
            async def mock_connect(*args, **kwargs):
                mock_writer = mock.MagicMock()
                mock_writer.wait_closed = mock.AsyncMock()
                return mock.MagicMock(), mock_writer
            
            with mock.patch("asyncio.open_connection", side_effect=mock_connect):
                cand_dir = os.path.join(runner.arena_dir, "worktrees", "cand_0")
                os.makedirs(cand_dir, exist_ok=True)
                runner._find_free_port = mock.MagicMock(return_value=1234)
                
                await runner._start_agent_server("agent_0", 1234)
                
                _, kwargs = mock_exec.call_args
                env = kwargs.get("env", {})
                config_json = env["OPENCODE_CONFIG_CONTENT"]
                
                # Strict validation: do not allow extra fields
                try:
                    config_obj = StrictConfig.model_validate_json(config_json)
                    self.assertIsInstance(config_obj, Config)
                    self.assertEqual(getattr(config_obj, "model", None), "google/gemini")
                    # Verify snapshot is explicitly False
                    self.assertFalse(getattr(config_obj, "snapshot", True))
                except Exception as e:
                    self.fail(f"Config validation failed (STRICT MODE). JSON: {config_json}. Error: {e}")

    async def test_shark_path_masking(self):
        """Verifies Shark masks absolute paths in the state prompt."""
        shark = Shark("agent_0")
        state = MarketState(round_num=1, liquidity_b=100.0, prompt="test")
        
        # Setup assets with absolute paths
        state.assets["cand_0"] = MarketAsset(
            id="cand_0", type="CANDIDATE", description="Self",
            code_path="/tmp/secret_path/agent_0_workspace"
        )
        state.assets["cand_1"] = MarketAsset(
            id="cand_1", type="CANDIDATE", description="Rival",
            code_path="/tmp/secret_path/rival_workspace"
        )
        
        # Mock get_candidate_diff to prevent git/FS calls
        with mock.patch("market.agents.shark.Shark.get_action", new_callable=mock.AsyncMock):
            prompt = await shark._format_state_prompt(state)
            
            # 1. Absolute paths MUST NOT be in the prompt
            self.assertNotIn("/tmp/secret_path", prompt)
            
            # 2. Privacy: Rival path must be hidden entirely
            self.assertNotIn("rival_workspace", prompt)
            
            # 3. Context: Self path should be masked with logical marker
            self.assertIn("Your Workspace", prompt)
            self.assertIn("./", prompt)
            
            # 4. Cleanup: Masking footer
            self.assertNotIn("To view full diff", prompt)

if __name__ == "__main__":
    unittest.main()
