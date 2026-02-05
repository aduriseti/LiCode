import unittest
import os
import tempfile
from market.logic.oracle import Oracle

class TestOracle(unittest.TestCase):
    
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
            
        # 4. Valid Test
        self.valid_test = os.path.join(self.tmp_dir, "test_valid.py")
        with open(self.valid_test, "w") as f:
            f.write("import solution\nassert solution.add(1, 2) == 3")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir)

    def test_pass(self):
        res = Oracle.run_test(self.good_cand, self.valid_test)
        self.assertEqual(res, "PASS")
        
    def test_fail(self):
        res = Oracle.run_test(self.bad_cand, self.valid_test)
        self.assertEqual(res, "FAIL")
        
    def test_timeout(self):
        # We need the TEST to call the function
        res = Oracle.run_test(self.loop_cand, self.valid_test, timeout=1)
        self.assertEqual(res, "TIMEOUT")
        
    def test_missing_file(self):
        res = Oracle.run_test("ghost.py", self.valid_test)
        self.assertEqual(res, "ERROR")

if __name__ == '__main__':
    unittest.main()
