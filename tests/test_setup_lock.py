import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from argparse import Namespace
import evaluate_swe_bench
from market.common.evaluator import StatusManager, SWEBenchInstanceRunner

@pytest.mark.asyncio
async def test_setup_lock_concurrency(tmp_path):
    """
    Test that run_instance respects the setup_lock.
    We run two instances and verify that they don't enter the 'make setup' section concurrently.
    """
    instance1 = {
        'instance_id': 'inst1',
        'repo': 'test/repo',
        'base_commit': 'abc',
        'problem_statement': 'Fix.'
    }
    instance2 = {
        'instance_id': 'inst2',
        'repo': 'test/repo',
        'base_commit': 'def',
        'problem_statement': 'Fix.'
    }

    args = Namespace(
        dummy=False,
        agents=1,
        rounds=1,
        output=str(tmp_path / "predictions.jsonl"),
        max_retries=1,
        initial_backoff=1.0,
        max_backoff=1.0
    )

    # We use a semaphore of 2 to allow both to run in parallel up to the lock
    semaphore = asyncio.Semaphore(2)

    setup_call_count = 0
    max_concurrent_setups = 0
    lock_acquired_count = 0

    async def mock_setup_exec(*args, **kwargs):
        nonlocal setup_call_count, max_concurrent_setups
        setup_call_count += 1
        max_concurrent_setups = max(max_concurrent_setups, setup_call_count)
        await asyncio.sleep(0.1) # Simulate some work
        setup_call_count -= 1

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        return mock_proc

    async def mock_generic_exec(*args, **kwargs):
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.wait = AsyncMock(return_value=None)
        mock_proc.returncode = 0
        return mock_proc

    async def mock_exec_side_effect(*cmd, **kwargs):
        if "make" in cmd and "setup" in cmd:
            return await mock_setup_exec(*cmd, **kwargs)
        return await mock_generic_exec(*cmd, **kwargs)

    # Create a real lock but wrap its acquire/release to track it
    real_lock = asyncio.Lock()
    original_acquire = real_lock.acquire

    async def tracked_acquire():
        nonlocal lock_acquired_count
        lock_acquired_count += 1
        return await original_acquire()

    real_lock.acquire = tracked_acquire

    status_mgr = StatusManager()
    runner = SWEBenchInstanceRunner(status_mgr, real_lock)

    async def mock_run_tournament(instance_id, work_dir, container_id, args):
        mock_orch = MagicMock()
        mock_orch.get_winner_id.return_value = "winner"
        mock_orch.get_winner_diff.return_value = "patch"
        mock_orch.worktrees_dir = "/tmp"
        return mock_orch

    with patch('market.common.evaluator.asyncio.create_subprocess_exec', side_effect=mock_exec_side_effect) as mock_exec, \
         patch('market.common.evaluator.docker') as mock_docker, \
         patch('market.common.evaluator.os.makedirs'), \
         patch('market.common.evaluator.open', MagicMock()), \
         patch('market.common.evaluator.os.path.abspath', return_value=str(tmp_path)), \
         patch('market.common.evaluator.os.path.exists', return_value=True), \
         patch('market.common.evaluator.shutil.rmtree'), \
         patch('market.common.evaluator.get_patch_from_winner', return_value="patch"):

        mock_docker.get_image_name.return_value = "img"
        mock_docker.pull_image = AsyncMock()
        mock_docker.start_container = AsyncMock(return_value="cont")
        mock_docker.stop_container = AsyncMock()

        # Run both concurrently
        await asyncio.gather(
            runner.run_instance(instance1, args, semaphore, mock_run_tournament),
            runner.run_instance(instance2, args, semaphore, mock_run_tournament)
        )

    # Check assertions
    assert lock_acquired_count == 2, f"Lock should have been acquired 2 times, but was {lock_acquired_count}"
    assert max_concurrent_setups == 1, f"Max concurrent setups should be 1, but was {max_concurrent_setups}"
