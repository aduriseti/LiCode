import os
import sys
import psutil
import asyncio
import unittest
import time
import uuid
import pytest
from market.common.oracle import CommonOracle, ResultType

class TestRAIIOracle(unittest.TestCase):
    @pytest.mark.timeout(60)
    def test_oracle_raii_cleanup(self):
        """
        Verifies that CommonOracle.run_test (via RAII context managers)
        successfully cleans up background processes.
        """
        import tempfile
        import shutil
        
        test_uuid = str(uuid.uuid4())
        test_dir = tempfile.mkdtemp()
        cand_dir = tempfile.mkdtemp()
        
        try:
            # Script that spawns a background process tagged with our UUID
            with open(os.path.join(test_dir, "run.sh"), "w") as f:
                f.write(f"#!/bin/bash\nnohup bash -c 'LICODE_TEST_UUID={test_uuid} sleep 1000' >/dev/null 2>&1 &\necho 'Started background process'\nexit 0\n")
            os.chmod(os.path.join(test_dir, "run.sh"), 0o755)
            
            async def run():
                # We also tag the oracle run itself
                os.environ["LICODE_TEST_UUID"] = test_uuid
                result, stdout, stderr = await CommonOracle.run_test(
                    candidate_dir=cand_dir,
                    verifier_dir=test_dir
                )
                return result

            result = asyncio.run(run())
            self.assertEqual(result, ResultType.PASS)
            
            # Give OS a moment to process kills
            time.sleep(2)
            
            # Sweep system for ANY process with our UUID
            leaked_pids = []
            for proc in psutil.process_iter(['pid', 'environ', 'cmdline']):
                try:
                    env = proc.info.get('environ') or {}
                    cmdline = proc.info.get('cmdline') or []
                    if env.get("LICODE_TEST_UUID") == test_uuid or any(test_uuid in arg for arg in cmdline):
                        leaked_pids.append(proc.pid)
                        proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            self.assertEqual(len(leaked_pids), 0, f"RAII Oracle leaked processes with UUID {test_uuid}: {leaked_pids}")
            
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)
            shutil.rmtree(cand_dir, ignore_errors=True)

if __name__ == '__main__':
    unittest.main()
