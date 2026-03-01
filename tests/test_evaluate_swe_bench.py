import os
import sys
import pytest
import asyncio
from unittest.mock import patch, MagicMock
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
        output=str(tmp_path / "run_folder" / "predictions.jsonl")
    )
    
    semaphore = asyncio.Semaphore(1)
    
    # Patch subprocess utilities
    with patch('evaluate_swe_bench.asyncio.create_subprocess_exec') as mock_exec:
        # Mock git clone/checkout processes
        mock_proc = MagicMock()
        mock_proc.communicate = MagicMock(side_effect=lambda: asyncio.sleep(0)) # Lambda returning coroutine
        mock_proc.wait = MagicMock(side_effect=lambda: asyncio.sleep(0))
        
        async def mock_communicate():
            return b"", b""
        mock_proc.communicate = mock_communicate
        
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
    assert len(table.columns) == 4
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
        mock_run_result = MagicMock()
        mock_run_result.stdout = "diff --git a/test.py b/test.py\n+print('fixed')"
        mock_run.return_value = mock_run_result
        
        patch_text = evaluate_swe_bench.get_patch_from_winner(str(tmp_path), report, state)
        
        assert patch_text == "diff --git a/test.py b/test.py\n+print('fixed')"
        
        # Verify the correct git commands were called
        mock_run.assert_any_call(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        mock_run.assert_any_call(["git", "reset", "problem.md"], cwd=str(tmp_path), capture_output=True)
        mock_run.assert_any_call(["git", "diff", "--cached", "HEAD"], cwd=str(tmp_path), capture_output=True, text=True)
