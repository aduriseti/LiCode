import atexit
import logging
import psutil
import os
import signal
import asyncio
import sys
from contextlib import asynccontextmanager
from typing import Set, Any, Dict, List

logger = logging.getLogger(__name__)

class ProcessRegistry:
    """
    Centralized process factory and manager.
    Ensures every spawned process is tagged, isolated in a new PGID, 
    and forcefully cleaned up on exit using RAII.
    """
    def __init__(self):
        self._registered = False

    def setup(self):
        """Registers the failsafe exit hooks."""
        if not self._registered:
            atexit.register(self.cleanup_all)
            # Register signal handlers to ensure cleanup on exit signals
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    signal.signal(sig, self._handle_signal)
                except (ValueError, RuntimeError):
                    # Fails if not in main thread
                    pass
            self._registered = True

    def _handle_signal(self, signum, frame):
        logger.info(f"ProcessRegistry: Received signal {signum}, performing failsafe cleanup...")
        self.cleanup_all()
        sys.exit(0)

    @asynccontextmanager
    async def spawn(self, *cmd, **kwargs):
        """
        Async context manager that spawns a managed process.
        Automatically injects tagging and ensures PGID-level cleanup on exit.
        """
        env = kwargs.get("env", os.environ).copy()
        current_pid = os.getpid()
        env["LICODE_MANAGED_BY"] = str(current_pid)
        kwargs["env"] = env
        kwargs["start_new_session"] = True
        
        is_shell = kwargs.pop("shell", False)
        
        if is_shell:
            proc = await asyncio.create_subprocess_shell(cmd[0], **kwargs)
        else:
            proc = await asyncio.create_subprocess_exec(*cmd, **kwargs)
        
        try:
            yield proc
        finally:
            # RAII Cleanup: Wipe the entire process tree safely
            try:
                # Close any open pipes to prevent deadlocks during wait
                for pipe in [proc.stdin, proc.stdout, proc.stderr]:
                    if pipe and hasattr(pipe, 'close'):
                        try: pipe.close()
                        except Exception: pass
                
                await self.kill_process_tree(proc)
            except Exception as e:
                logger.debug(f"ProcessRegistry: cleanup failed for PID {proc.pid}: {e}")

    async def kill_process_tree(self, proc: asyncio.subprocess.Process, timeout: float = 2.0):
        """
        Idiomatically and safely terminates an asyncio process and all its descendants using psutil.
        """
        pid = proc.pid
        
        # Try to get the process object. If it's already dead, we still want to 
        # sweep for orphans that might have been left behind.
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            processes = children + [parent]
        except psutil.NoSuchProcess:
            # Parent is already dead, but orphans might exist.
            # We don't have an easy way to find them without a full sweep
            # or knowing the PGID. Since we use start_new_session=True,
            # the PGID was the same as the original PID.
            processes = []
            for p in psutil.process_iter(['pid', 'name', 'environ', 'cmdline']):
                try:
                    # Check if it's an orphan from this specific spawn
                    # We look for the tag in cmdline or environment
                    info = p.info
                    env = info.get('environ') or {}
                    cmdline = info.get('cmdline') or []
                    current_pid = os.getpid()
                    tag_str = f"--licode-managed-by={current_pid}"
                    
                    if env.get("LICODE_MANAGED_BY") == str(current_pid) or any(arg == tag_str for arg in cmdline):
                        # This looks like it belonged to us.
                        # However, we only want to kill it if it's related to THIS specific spawn?
                        # Actually, kill_process_tree is called on context exit.
                        # It's safer to just rely on cleanup_all for orphans if the parent is already gone,
                        # UNLESS we can identify this specific child.
                        pass
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        # If we found processes, kill them
        if processes:
            # 1. Soft terminate
            for p in processes:
                try:
                    if p.pid > 100:
                        p.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # 2. Wait for graceful exit
            _, alive = psutil.wait_procs(processes, timeout=timeout)

            # 3. Hard kill survivors
            for p in alive:
                try:
                    if p.pid > 100:
                        p.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        # 4. Final attempt to reap the asyncio process
        try:
            if hasattr(proc, 'wait'):
                await asyncio.wait_for(proc.wait(), timeout=1.0)
        except (asyncio.TimeoutError, ProcessLookupError, Exception):
            pass

    def cleanup_all(self):
        """
        Failsafe: Sweeps the system for any descendants or orphans tagged with LICODE_MANAGED_BY.
        """
        current_pid = os.getpid()
        tag_str = f"--licode-managed-by={current_pid}"
        killed_procs = []
        
        # 1. Collect all processes to kill
        for proc in psutil.process_iter(['pid', 'cmdline', 'environ', 'name']):
            try:
                if proc.pid <= 100 or proc.pid == current_pid:
                    continue
                
                info = proc.info
                cmdline = info.get('cmdline') or []
                is_ours = any(arg == tag_str for arg in cmdline)
                
                if not is_ours:
                    env = info.get('environ') or {}
                    if env.get("LICODE_MANAGED_BY") == str(current_pid):
                        is_ours = True
                
                if is_ours:
                    killed_procs.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # 2. Add descendants of current process
        try:
            me = psutil.Process()
            for child in me.children(recursive=True):
                if child.pid > 100 and child not in killed_procs:
                    killed_procs.append(child)
        except psutil.NoSuchProcess:
            pass

        if not killed_procs:
            return

        # 3. Soft terminate all
        for p in killed_procs:
            try:
                p.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # 4. Wait a moment
        _, alive = psutil.wait_procs(killed_procs, timeout=1.0)

        # 5. Hard kill survivors
        for p in alive:
            try:
                logger.info(f"ProcessRegistry: Force killing stubborn process {p.pid}")
                p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        logger.debug(f"ProcessRegistry: Failsafe swept {len(killed_procs)} processes.")

# Global singleton
registry = ProcessRegistry()
# Auto-register on import so it's always active
registry.setup()
