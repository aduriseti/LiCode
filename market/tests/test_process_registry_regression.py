import asyncio
import os
import signal
import psutil
import pytest
from unittest.mock import patch, MagicMock
from market.common.process_registry import ProcessRegistry

@pytest.mark.asyncio
async def test_spawn_raii_cleanup():
    """Verifies that spawning a process via RAII cleans it up on exit."""
    registry = ProcessRegistry()
    
    proc_pid = None
    async with registry.spawn("sleep", "10") as proc:
        proc_pid = proc.pid
        assert psutil.pid_exists(proc_pid)
        # Process should be alive during context
        p = psutil.Process(proc_pid)
        assert p.is_running()

    # After context, process should be dead
    await asyncio.sleep(0.5) # Give it a moment to reap
    assert not psutil.pid_exists(proc_pid)

@pytest.mark.asyncio
async def test_kill_process_tree_recursive():
    """Verifies that kill_process_tree kills both parent and descendants."""
    registry = ProcessRegistry()
    
    # Spawn a shell that spawns a sleep
    proc = await asyncio.create_subprocess_exec(
        "bash", "-c", "sleep 100 & sleep 100",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True
    )
    
    parent_pid = proc.pid
    psutil_parent = psutil.Process(parent_pid)
    
    # Wait for children to appear
    for _ in range(10):
        children = psutil_parent.children(recursive=True)
        if len(children) >= 2:
            break
        await asyncio.sleep(0.1)
    
    children_pids = [c.pid for c in psutil_parent.children(recursive=True)]
    assert len(children_pids) >= 2
    
    # Kill the tree
    await registry.kill_process_tree(proc)
    
    # Verify all are dead
    all_pids = [parent_pid] + children_pids
    for pid in all_pids:
        assert not psutil.pid_exists(pid), f"Process {pid} should have been killed"

@pytest.mark.asyncio
async def test_pid_floor_protection():
    """Mocks psutil to verify that PIDs <= 100 are never targeted for termination."""
    registry = ProcessRegistry()
    
    # We mock psutil.Process and its methods
    mock_proc = MagicMock()
    mock_proc.pid = 42 # Below floor
    mock_proc.returncode = None
    
    with patch("psutil.Process") as mock_psutil_proc_class:
        mock_p_instance = MagicMock()
        mock_p_instance.pid = 42
        mock_p_instance.children.return_value = []
        mock_psutil_proc_class.return_value = mock_p_instance
        
        await registry.kill_process_tree(mock_proc)
        
        # Verify terminate/kill was NEVER called on the mock instance
        assert mock_p_instance.terminate.call_count == 0
        assert mock_p_instance.kill.call_count == 0

@pytest.mark.asyncio
async def test_cleanup_all_orphan_sweep():
    """Verifies that cleanup_all correctly identifies and kills tagged orphans."""
    registry = ProcessRegistry()
    current_pid = os.getpid()
    
    # Manually spawn a process with the tag but NOT managed by our current RAII context
    # This simulates a process left over from a crash
    tag_str = f"--licode-managed-by={current_pid}"
    orphan = subprocess_proc = await asyncio.create_subprocess_exec(
        "sleep", "100", tag_str,
        start_new_session=True
    )
    
    orphan_pid = orphan.pid
    assert psutil.pid_exists(orphan_pid)
    
    # Run the sweep
    registry.cleanup_all()
    
    # Orphan should be terminated (it sends SIGTERM first now)
    await asyncio.sleep(0.2)
    assert not psutil.pid_exists(orphan_pid)

@pytest.mark.asyncio
async def test_cleanup_all_environment_match():
    """Verifies that cleanup_all correctly identifies orphans via environment variables."""
    registry = ProcessRegistry()
    current_pid = os.getpid()
    
    env = os.environ.copy()
    env["LICODE_MANAGED_BY"] = str(current_pid)
    
    orphan = await asyncio.create_subprocess_exec(
        "sleep", "100",
        env=env,
        start_new_session=True
    )
    
    orphan_pid = orphan.pid
    assert psutil.pid_exists(orphan_pid)
    
    # Run the sweep
    registry.cleanup_all()
    
    await asyncio.sleep(0.2)
    assert not psutil.pid_exists(orphan_pid)
