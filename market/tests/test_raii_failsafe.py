import os
import sys
import psutil
import subprocess
import unittest
import time
import uuid
import pytest

class TestRAIIFailsafe(unittest.TestCase):
    @pytest.mark.timeout(60)
    def test_failsafe_reap(self):
        """
        Verifies that ProcessRegistry kills 'orphan' processes tagged with LICODE_MANAGED_BY
        even if the parent process crashes (bypassing RAII context managers).
        """
        test_uuid = str(uuid.uuid4())
        
        simulator_script = f"""
import os
import sys
import asyncio
import time
from market.common.process_registry import registry

async def run():
    env = os.environ.copy()
    env["LICODE_TEST_UUID"] = "{test_uuid}"
    
    # Use registry.spawn context manager but exit the WHOLE PROCESS 
    # while inside the context to see if atexit catches it.
    async with registry.spawn("sleep", "1000", env=env) as proc:
        print(f"SPAWNED_PID:{{proc.pid}}", flush=True)
        await asyncio.sleep(1)
        sys.exit(0)

if __name__ == '__main__':
    asyncio.run(run())
"""
        script_path = "failsafe_simulator.py"
        with open(script_path, "w") as f:
            f.write(simulator_script)
            
        try:
            # Run simulator
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True
            )
            
            # Extract spawned PID from output
            spawned_pid = None
            for line in result.stdout.splitlines():
                if "SPAWNED_PID:" in line:
                    spawned_pid = int(line.split(":")[1])
                    break
            
            self.assertIsNotNone(spawned_pid, "Failed to get spawned PID from simulator")
            
            # Give OS time to process kills from the simulator's atexit hook
            time.sleep(3)
            
            # Verify orphan is dead
            self.assertFalse(psutil.pid_exists(spawned_pid), f"Orphan process {spawned_pid} still alive!")
            
            # Final safety sweep for any process with the UUID
            for proc in psutil.process_iter(['pid', 'environ', 'cmdline']):
                try:
                    env = proc.info.get('environ') or {}
                    cmdline = proc.info.get('cmdline') or []
                    if env.get("LICODE_TEST_UUID") == test_uuid or any(test_uuid in arg for arg in cmdline):
                        self.fail(f"Found leaked process with UUID {test_uuid}: PID {proc.pid}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                    
        finally:
            if os.path.exists(script_path):
                os.remove(script_path)

if __name__ == '__main__':
    unittest.main()
