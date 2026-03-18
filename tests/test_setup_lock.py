import os
import sys
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from argparse import Namespace

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import evaluate_swe_bench

@pytest.mark.asyncio
async def test_setup_lock_concurrency(tmp_path):
    """
    Test that run_market_on_instance respects the setup_lock.
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
        dummy=True,
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

    # Create a real lock but wrap its __aenter__ to track it
    real_lock = asyncio.Lock()
    
    async def tracked_aenter(*args, **kwargs):
        nonlocal lock_acquired_count
        lock_acquired_count += 1
        return await real_lock.__aenter__()

    async def tracked_aexit(*args, **kwargs):
        return await real_lock.__aexit__(*args, **kwargs)

    mock_lock = MagicMock(spec=asyncio.Lock)
    mock_lock.__aenter__ = AsyncMock(side_effect=tracked_aenter)
    mock_lock.__aexit__ = AsyncMock(side_effect=tracked_aexit)

    with patch('evaluate_swe_bench.asyncio.create_subprocess_exec', side_effect=mock_exec_side_effect) as mock_exec, \
         patch('evaluate_swe_bench.docker') as mock_docker, \
         patch('evaluate_swe_bench.setup_lock', mock_lock), \
         patch('evaluate_swe_bench.os.makedirs'), \
         patch('evaluate_swe_bench.open', MagicMock()), \
         patch('evaluate_swe_bench.os.path.abspath', return_value=str(tmp_path)), \
         patch('evaluate_swe_bench.os.path.exists', return_value=True), \
         patch('shutil.rmtree'), \
         patch('evaluate_swe_bench.logger'):

        mock_docker.get_image_name.return_value = "img"
        mock_docker.pull_image = AsyncMock()
        mock_docker.start_container = AsyncMock(return_value="cont")
        mock_docker.stop_container = AsyncMock()

        # Run both concurrently
        await asyncio.gather(
            evaluate_swe_bench.run_market_on_instance(instance1, args, semaphore),
            evaluate_swe_bench.run_market_on_instance(instance2, args, semaphore)
        )

        # Verify that setup was called twice
        assert lock_acquired_count == 2
        # Verify that they NEVER ran concurrently
        assert max_concurrent_setups == 1
