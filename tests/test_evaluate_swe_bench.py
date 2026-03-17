import os
import sys
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from argparse import Namespace

# Add project root to sys.path so we can import evaluate_swe_bench
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import evaluate_swe_bench

@pytest.mark.asyncio
async def test_run_market_dummy_mode(tmp_path):
    """
    Test that when args.dummy is True, the system bypasses the market orchestrator,
    creates the workspace, writes the problem, and returns an empty patch.
    """
    instance = {
        'instance_id': 'test_repo__test_issue-123',
        'repo': 'test/repo',
        'base_commit': 'abcdef123456',
        'problem_statement': 'Fix the bug.'
    }
    
    args = Namespace(
        dummy=True,
        agents=3,
        rounds=5,
        provider=None,
        model=None,
        output=str(tmp_path / "run_folder" / "predictions.jsonl"),
        max_retries=3,
        initial_backoff=120.0,
        max_backoff=1000.0
    )
    
    semaphore = asyncio.Semaphore(1)
    
    # Patch subprocess utilities and docker
    with patch('evaluate_swe_bench.asyncio.create_subprocess_exec') as mock_exec, \
         patch('evaluate_swe_bench.docker') as mock_docker:
        
        # Mock docker methods
        mock_docker.get_image_name.return_value = "test_image"
        mock_docker.pull_image = MagicMock(side_effect=lambda x: asyncio.sleep(0))
        mock_docker.start_container = MagicMock(side_effect=lambda *args: asyncio.sleep(0, result="test_container_id"))
        
        async def mock_async_docker_start(*args, **kwargs):
            return "test_container_id"
        mock_docker.start_container = mock_async_docker_start
        
        async def mock_async_none(*args, **kwargs):
            return None
        mock_docker.pull_image = mock_async_none
        mock_docker.stop_container = mock_async_none

        # Mock git clone/checkout/bootstrap processes
        mock_proc = MagicMock()
        mock_proc.communicate = mock_async_none
        mock_proc.wait = mock_async_none
        mock_proc.returncode = 0
        
        mock_exec.return_value = mock_proc
        
        # Patch the base path for workspaces to use tmp_path
        original_abspath = os.path.abspath
        def mock_abspath(path):
            if "run_folder" in path:
                return str(tmp_path / "run_folder" / "predictions.jsonl")
            return original_abspath(path)
            
        with patch('evaluate_swe_bench.os.path.abspath', side_effect=mock_abspath):
            result = await evaluate_swe_bench.run_market_on_instance(instance, args, semaphore)
            
            # 1. Assert correct result format
            assert result is not None
            assert result['instance_id'] == 'test_repo__test_issue-123'
            assert result['model_patch'] == ''
            assert result['model_name_or_path'] == 'dummy-test-agent'
            
            # 2. Verify the workspace directory was created
            workspace_dir = tmp_path / "run_folder" / "workspaces" / "test_repo__test_issue-123"
            assert workspace_dir.exists()
            assert (workspace_dir / 'problem.md').exists()
            with open(workspace_dir / 'problem.md', 'r') as f:
                assert f.read() == 'Fix the bug.'

from rich.table import Table

def test_generate_table():
    """
    Test that the generate_table function correctly processes the global status_map.
    """
    import time
    # Clear and populate the global status_map for the test
    evaluate_swe_bench.status_map.clear()
    
    start = time.time()
    evaluate_swe_bench.status_map["test-issue-1"] = {
        "status": "Running Round 1",
        "start_time": start - 10,
        "stages": [
            {"name": "Cloning", "start_time": start - 10, "duration": 5},
            {"name": "Starting Round 1", "start_time": start - 5, "duration": 0}
        ]
    }
    
    table = evaluate_swe_bench.generate_table()
    
    # 1. Assert it's a rich Table object
    assert isinstance(table, Table)
    assert table.title == "OpenCode Market: SWE-bench Evaluation"
    
    # 2. Verify columns and presence of data
    assert len(table.columns) == 5
    # Rich table data is not easily accessible via public API without rendering,
    # but we can check if it runs without error and has the title we expect.

def test_generate_table_dynamic_updates():
    """
    Test that generate_table reflects real-time changes in status_map.
    """
    import time
    evaluate_swe_bench.status_map.clear()
    
    # 1. Start with an empty map
    table = evaluate_swe_bench.generate_table()
    assert table.row_count == 0
    
    # 2. Add an item and verify it appears
    evaluate_swe_bench.status_map["issue-1"] = {
        "status": "Test Status",
        "start_time": time.time(),
        "stages": []
    }
    table = evaluate_swe_bench.generate_table()
    assert table.row_count == 1
    
    # 3. Verify it works as a callable (Option A)
    from rich.live import Live
    with Live(get_renderable=evaluate_swe_bench.generate_table, refresh_per_second=1):
        evaluate_swe_bench.status_map["issue-2"] = {
            "status": "Another Status",
            "start_time": time.time(),
            "stages": []
        }
        # Just verifying it doesn't crash when called by Live
        final_table = evaluate_swe_bench.generate_table()
        assert final_table.row_count == 2

def test_get_patch_from_winner(tmp_path):
    """
    Test that the winning candidate's patch is extracted correctly.
    """
    report = "**Winner:** candidate_1 (Market Confidence: 100%)"
    state = {
        "round_num": 1,
        "liquidity_b": 100.0,
        "whale_wealth": 1000.0,
        "assets": {
            "candidate_1": {
                "id": "candidate_1",
                "type": "CANDIDATE",
                "description": "desc",
                "code_path": str(tmp_path),
                "q_yes": 500.0,
                "q_no": 0.0
            }
        },
        "agents": {}
    }
    
    with patch('evaluate_swe_bench.subprocess.run') as mock_run:
        def mock_run_side_effect(cmd, **kwargs):
            m = MagicMock()
            if cmd[1] == "log":
                m.stdout = "abc123baseline"
            elif cmd[1] == "diff":
                m.stdout = "diff --git a/test.py b/test.py\n+print('fixed')"
            else:
                m.stdout = ""
            return m
            
        mock_run.side_effect = mock_run_side_effect
        
        patch_text = evaluate_swe_bench.get_patch_from_winner(str(tmp_path), report, state)
        
        assert patch_text == "diff --git a/test.py b/test.py\n+print('fixed')"
        
        # Verify the correct git commands were called
        mock_run.assert_any_call(["git", "log", "--grep=Initial Baseline", "--format=%H", "-n", "1"], cwd=str(tmp_path), capture_output=True, text=True)
        mock_run.assert_any_call(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        mock_run.assert_any_call(["git", "reset", "abc123baseline", "problem.md"], cwd=str(tmp_path), capture_output=True)
        mock_run.assert_any_call(["git", "diff", "--cached", "abc123baseline"], cwd=str(tmp_path), capture_output=True, text=True)

import json

@pytest.mark.asyncio
async def test_run_market_protocol_fix(tmp_path):
    """
    Test that run_market_on_instance correctly extracts the final result
    even if the "type": "final_result" tag is missing, as long as "state" and "report" are present.
    """
    instance = {
        'instance_id': 'test_repo__test_issue-456',
        'repo': 'test/repo',
        'base_commit': 'abcdef123456',
        'problem_statement': 'Fix the bug.'
    }
    
    args = Namespace(
        dummy=False,
        agents=1,
        rounds=1,
        provider='test-provider',
        model='test-model',
        output=str(tmp_path / "run_folder" / "predictions.jsonl"),
        dashboard=False,
        max_retries=3,
        initial_backoff=120.0,
        max_backoff=1000.0
    )
    semaphore = asyncio.Semaphore(1)
    
    # Mock data with the "state" and "report" but NO "type": "final_result" tag
    mock_output = {
        "state": {"round_num": 1, "assets": {"winner": {"type": "CANDIDATE", "code_path": "/tmp"}}},
        "report": "**Winner:** winner"
    }
    
    with patch('evaluate_swe_bench.asyncio.create_subprocess_exec') as mock_exec, \
         patch('evaluate_swe_bench.get_patch_from_winner', return_value="fake-patch"), \
         patch('evaluate_swe_bench.docker') as mock_docker:
        
        # Mock docker
        async def mock_async_val(val):
            return val
        async def mock_async_none(*args, **kwargs):
            return None
            
        mock_docker.get_image_name.return_value = "test_image"
        mock_docker.pull_image = mock_async_none
        mock_docker.start_container = MagicMock(side_effect=lambda *args: mock_async_val("test_container_id"))
        mock_docker.stop_container = mock_async_none
    
        # We need mocks for clone, checkout, git-safe, bootstrap, market run, and chown
        # Order in evaluate_swe_bench.py:
        # 1. git clone
        # 2. git checkout
        # 3. git config safe.directory (git_safe_proc)
        # 4. pip install (bootstrap_proc)
        # 5. market.cli (process)
        # 6. chown (chown_proc)
        
        mock_clone = MagicMock()
        mock_clone.communicate = mock_async_none
        mock_clone.wait = mock_async_none
        mock_clone.returncode = 0
        
        mock_checkout = MagicMock()
        mock_checkout.communicate = mock_async_none
        mock_checkout.wait = mock_async_none
        mock_checkout.returncode = 0

        mock_git_safe = MagicMock()
        mock_git_safe.communicate = mock_async_none
        mock_git_safe.returncode = 0

        mock_bootstrap = MagicMock()
        mock_bootstrap.communicate = mock_async_none
        mock_bootstrap.returncode = 0
        
        mock_market = MagicMock()
        mock_market.wait = mock_async_none
        mock_market.returncode = 0

        mock_chown = MagicMock()
        mock_chown.communicate = mock_async_none
        mock_chown.returncode = 0
        
        # Setup market stdout
        mock_stdout = MagicMock()
        lines = [
            json.dumps({"type": "log", "message": "Starting Round 1"}).encode() + b"\n",
            json.dumps(mock_output).encode() + b"\n",
            b"" # EOF
        ]
        
        async def mock_readline():
            if not lines:
                return b""
            return lines.pop(0)
        
        mock_stdout.readline = mock_readline
        mock_market.stdout = mock_stdout
        
        mock_exec.side_effect = [mock_clone, mock_checkout, mock_git_safe, mock_bootstrap, mock_market, mock_chown]
        
        # Patch directory operations
        with patch('evaluate_swe_bench.os.makedirs'), \
             patch('evaluate_swe_bench.open', MagicMock()):
            
            result = await evaluate_swe_bench.run_market_on_instance(instance, args, semaphore)
            
            assert result is not None
            assert result['instance_id'] == 'test_repo__test_issue-456'
            assert result['model_patch'] == 'fake-patch'

@pytest.mark.asyncio
async def test_run_market_multiple_configs(tmp_path):
    """
    Test that run_market_on_instance correctly passes multiple models and providers
    to the market CLI command.
    """
    instance = {
        'instance_id': 'test_repo__test_issue-789',
        'repo': 'test/repo',
        'base_commit': 'abcdef123456',
        'problem_statement': 'Fix the bug.'
    }
    
    args = Namespace(
        dummy=False,
        agents=2,
        rounds=1,
        provider=['provider-a', 'provider-b'],
        model=['model-1', 'model-2'],
        output=str(tmp_path / "run_folder" / "predictions.jsonl"),
        dashboard=False,
        max_retries=1,
        initial_backoff=120.0,
        max_backoff=1000.0
    )
    semaphore = asyncio.Semaphore(1)
    
    mock_output = {
        "state": {"round_num": 1, "assets": {"winner": {"type": "CANDIDATE", "code_path": "/tmp"}}},
        "report": "**Winner:** winner"
    }
    
    with patch('evaluate_swe_bench.asyncio.create_subprocess_exec') as mock_exec, \
         patch('evaluate_swe_bench.get_patch_from_winner', return_value="fake-patch"), \
         patch('evaluate_swe_bench.docker') as mock_docker:
        
        async def mock_async_val(val): return val
        async def mock_async_none(*args, **kwargs): return None
            
        mock_docker.get_image_name.return_value = "test_image"
        mock_docker.pull_image = mock_async_none
        mock_docker.start_container = MagicMock(side_effect=lambda *args: mock_async_val("test_container_id"))
        mock_docker.stop_container = mock_async_none
    
        mock_market = MagicMock()
        mock_market.wait = mock_async_none
        mock_market.returncode = 0
        mock_stdout = MagicMock()
        mock_stdout.readline = AsyncMock(side_effect=[json.dumps(mock_output).encode() + b"\n", b""])
        mock_market.stdout = mock_stdout
        
        # We only care about the market.cli call
        def exec_side_effect(*cmd, **kwargs):
            if "market.cli" in cmd:
                return mock_market
            m = MagicMock()
            m.communicate = mock_async_none
            m.wait = mock_async_none
            m.returncode = 0
            return m
            
        mock_exec.side_effect = exec_side_effect
        
        with patch('evaluate_swe_bench.os.makedirs'), \
             patch('evaluate_swe_bench.open', MagicMock()):
            
            await evaluate_swe_bench.run_market_on_instance(instance, args, semaphore)
            
            # Find market.cli call and verify args
            market_call = None
            for call in mock_exec.call_args_list:
                if "market.cli" in call[0]:
                    market_call = call[0]
                    break
            
            assert market_call is not None
            # Check for multiple --model and --provider arguments
            # market_cmd.extend(["--provider"] + args.provider) -> ... --provider provider-a provider-b
            market_call_list = list(market_call)
            
            prov_idx = market_call_list.index("--provider")
            assert market_call_list[prov_idx+1] == "provider-a"
            assert market_call_list[prov_idx+2] == "provider-b"
            
            model_idx = market_call_list.index("--model")
            assert market_call_list[model_idx+1] == "model-1"
            assert market_call_list[model_idx+2] == "model-2"
