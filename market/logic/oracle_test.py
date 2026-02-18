import unittest
import os
import tempfile
import shutil
from market.logic.oracle import Oracle

class TestOracle(unittest.IsolatedAsyncioTestCase):
    
    def setUp(self):
        # Create dummy files
        self.tmp_dir = tempfile.mkdtemp()
        
        # 1. Good Candidate
        self.good_cand = os.path.join(self.tmp_dir, "good.py")
        with open(self.good_cand, "w") as f:
            f.write("def add(a, b): return a + b")
            
        # 2. Bad Candidate
        self.bad_cand = os.path.join(self.tmp_dir, "bad.py")
        with open(self.bad_cand, "w") as f:
            f.write("def add(a, b): return a - b")
            
        # 3. Infinite Loop Candidate
        self.loop_cand = os.path.join(self.tmp_dir, "loop.py")
        with open(self.loop_cand, "w") as f:
            f.write("def add(a, b): \n while True: pass\n return 0")
            
        # 4. Valid Verifier Package
        self.valid_verifier_dir = os.path.join(self.tmp_dir, "v_valid")
        os.makedirs(self.valid_verifier_dir)
        
        # Write test.py that imports solution
        with open(os.path.join(self.valid_verifier_dir, "test.py"), "w") as f:
            f.write("import solution\nassert solution.add(1, 2) == 3")
            
        # Write run.sh
        run_sh = os.path.join(self.valid_verifier_dir, "run.sh")
        with open(run_sh, "w") as f:
            f.write("#!/bin/bash\npython3 test.py")
        os.chmod(run_sh, 0o755)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    async def test_pass(self):
        res = await Oracle.run_test(self.good_cand, self.valid_verifier_dir)
        self.assertEqual(res, "PASS")
        
    async def test_fail(self):
        res = await Oracle.run_test(self.bad_cand, self.valid_verifier_dir)
        self.assertEqual(res, "FAIL")
        
    async def test_timeout(self):
        # We need the TEST to call the function
        res = await Oracle.run_test(self.loop_cand, self.valid_verifier_dir, timeout=1)
        self.assertEqual(res, "TIMEOUT")
        
    async def test_missing_file(self):
        res = await Oracle.run_test("ghost.py", self.valid_verifier_dir)
        self.assertEqual(res, "ERROR")

if __name__ == '__main__':
    unittest.main()