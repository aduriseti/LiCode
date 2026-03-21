import atexit
import logging
import psutil
import os
import signal
import asyncio
import sys
from contextlib import asynccontextmanager
from typing import Set, Any, Dict, List, Optional

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
        Automatically isolated in a new PGID and cleaned up on exit.
        """
        env = kwargs.get("env", os.environ).copy()
        current_pid = os.getpid()
        env["LICODE_MANAGED_BY"] = str(current_pid)
        kwargs["env"] = env
        # Create a new process group for the entire tree
        kwargs["start_new_session"] = True
        
        is_shell = kwargs.pop("shell", False)
        
        if is_shell:
            proc = await asyncio.create_subprocess_shell(cmd[0], **kwargs)
        else:
            proc = await asyncio.create_subprocess_exec(*cmd, **kwargs)
        
        # Capture PGID immediately
        pgid = None
        try:
            pgid = os.getpgid(proc.pid)
        except:
            pass

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
                
                await self.kill_process_tree(proc, pgid=pgid)
            except Exception as e:
                logger.debug(f"ProcessRegistry: cleanup failed for PID {proc.pid}: {e}")

    async def kill_process_tree(self, proc: asyncio.subprocess.Process, pgid: Optional[int] = None, timeout: float = 2.0):
        """
        Idiomatically and safely terminates an asyncio process and all its descendants.
        Uses PGID-level termination for maximum reliability.
        """
        pid = proc.pid
        if pgid is None:
            try: pgid = os.getpgid(pid)
            except: pass

        # 1. Collect all processes in the group
        processes = []
        try:
            parent = psutil.Process(pid)
            processes = parent.children(recursive=True) + [parent]
        except psutil.NoSuchProcess:
            pass
            
        # 2. Add other processes sharing the same PGID (re-parented orphans)
        if pgid and pgid != os.getpgid(0):
            for p in psutil.process_iter(['pid']):
                try:
                    if os.getpgid(p.pid) == pgid and p not in processes:
                        processes.append(p)
                except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
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

            # 3. Hard kill survivors (and the whole group)
            if pgid and pgid != os.getpgid(0):
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
            
            for p in alive:
                try:
                    if p.pid > 100:
                        p.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        # 4. Final attempt to reap the asyncio handle
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
