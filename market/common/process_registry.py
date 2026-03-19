import atexit
import logging
import psutil

logger = logging.getLogger(__name__)

class ProcessRegistry:
    """
    Centralized process sweeper. Uses psutil and an atexit hook to ensure
    all descendant processes (like opencode servers and dashboards) are
    forcefully killed when the main Python process exits. This prevents 
    process leaks if a test crashes without explicitly closing runners.
    """
    def __init__(self):
        self._registered = False

    def setup(self):
        if not self._registered:
            atexit.register(self.cleanup_all)
            self._registered = True

    def cleanup_all(self):
        """
        Recursively finds all descendants of the current process and kills them.
        """
        try:
            current_process = psutil.Process()
            # We must get the list of descendants *before* we start killing them,
            # because killing a parent might detach its children (making them orphans)
            # and they would disappear from the children() list.
            descendants = current_process.children(recursive=True)
        except psutil.NoSuchProcess:
            return

        if not descendants:
            return
            
        logger.debug(f"ProcessRegistry: Sweeping {len(descendants)} orphaned child processes...")
        
        # Issue SIGKILL to all descendants
        for child in descendants:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
                
        # Wait a moment for them to actually terminate to avoid zombies
        psutil.wait_procs(descendants, timeout=3)

# Global singleton
registry = ProcessRegistry()
# Auto-register on import so it's always active
registry.setup()
