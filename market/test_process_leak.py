import os
import sys
import uuid
import psutil
import asyncio
import subprocess
import unittest
import time

class TestProcessLeak(unittest.TestCase):
    def test_market_runner_process_leaks(self):
        """
        Self-contained regression test for process leaks using the UUID tagging strategy.
        Spawns a simulator process that starts MarketRunner(dashboard=True) and then crashes without cleanup.
        Verifies that the psutil atexit sweeper correctly kills all descendants (including detached JS processes).
        """
        # Create a unique UUID to tag this specific test run
        test_uuid = str(uuid.uuid4())
        
        # Create a temporary simulator script
        simulator_script = """
import os
import sys
import asyncio
from market.runner import MarketRunner

async def main():
    # Initialize MarketRunner with dashboard, which spawns the node server, 
    # which in turn spawns the detached pty-helper.js and opencode processes.
    runner = MarketRunner(prompt="Test", n_agents=1, budget=100.0, dashboard=True)
    await runner.initialize(json_logs=True)
    
    # Intentionally crash without calling runner.close()
    # The atexit hook registered by market.common.process_registry should catch this
    # and recursively kill all descendants.
    print("Simulator crashing intentionally...", flush=True)
    sys.exit(1)

if __name__ == '__main__':
    # Ensure registry is loaded
    import market.common.process_registry
    asyncio.run(main())
"""
        script_path = "crash_simulator.py"
        with open(script_path, "w") as f:
            f.write(simulator_script)
            
        env = os.environ.copy()
        env["TEST_LEAK_UUID"] = test_uuid
        
        try:
            # 1. Run the simulator
            result = subprocess.run(
                [sys.executable, script_path],
                env=env,
                capture_output=True,
                text=True
            )
            
            # 2. Give the OS a moment to fully process the SIGKILLs issued by the atexit hook
            time.sleep(3)
            
            # 3. Sweep the entire system for surviving processes with our UUID
            leaked_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'environ', 'cmdline']):
                try:
                    # Accessing environ can throw AccessDenied for processes owned by other users
                    p_env = proc.info.get('environ') or {}
                    if p_env.get("TEST_LEAK_UUID") == test_uuid:
                        leaked_processes.append({
                            "pid": proc.info["pid"],
                            "name": proc.info["name"],
                            "cmdline": " ".join(proc.info.get("cmdline", []))
                        })
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    pass
                    
            if leaked_processes:
                leak_details = "\\n".join([f"PID {p['pid']} ({p['name']}): {p['cmdline']}" for p in leaked_processes])
                self.fail(f"Found {len(leaked_processes)} leaked processes!\\n{leak_details}")
                
        finally:
            if os.path.exists(script_path):
                os.remove(script_path)

if __name__ == '__main__':
    unittest.main()
