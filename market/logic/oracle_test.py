import os
import shutil
import tempfile
import unittest

from market.logic.oracle import Oracle


class TestOracle(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create dummy files
        self.tmp_dir = tempfile.mkdtemp()

        # 1. Good Candidate Directory
        self.good_cand_dir = os.path.join(self.tmp_dir, "good_cand")
        os.makedirs(self.good_cand_dir)
        with open(os.path.join(self.good_cand_dir, "solution.py"), "w") as f:
            f.write("def add(a, b): return a + b")

        # 2. Bad Candidate Directory
        self.bad_cand_dir = os.path.join(self.tmp_dir, "bad_cand")
        os.makedirs(self.bad_cand_dir)
        with open(os.path.join(self.bad_cand_dir, "solution.py"), "w") as f:
            f.write("def add(a, b): return a - b")

        # 3. Infinite Loop Candidate Directory
        self.loop_cand_dir = os.path.join(self.tmp_dir, "loop_cand")
        os.makedirs(self.loop_cand_dir)
        with open(os.path.join(self.loop_cand_dir, "solution.py"), "w") as f:
            f.write("def add(a, b): \n while True: pass\n return 0")

        # 4. Valid Verifier Package
        self.valid_verifier_dir = os.path.join(self.tmp_dir, "v_valid")
        os.makedirs(self.valid_verifier_dir)

        # Write test.py that imports solution
        # Since oracle copies candidate files to root, 'import solution' works if solution.py is in root
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
        res = await Oracle.run_test(self.good_cand_dir, self.valid_verifier_dir)
        self.assertEqual(res, "PASS")

    async def test_fail(self):
        res = await Oracle.run_test(self.bad_cand_dir, self.valid_verifier_dir)
        self.assertEqual(res, "FAIL")

    async def test_timeout(self):
        # We need the TEST to call the function
        res = await Oracle.run_test(self.loop_cand_dir, self.valid_verifier_dir, timeout=1)
        self.assertEqual(res, "TIMEOUT")

    async def test_missing_dir(self):
        res = await Oracle.run_test("/non/existent/dir", self.valid_verifier_dir)
        self.assertEqual(res, "ERROR")

    async def test_contract_enforcement(self):
        """Test that verifiers can enforce file structure contracts."""
        # Setup Candidate A (Follows contract: main.py)
        cand_a = os.path.join(self.tmp_dir, "cand_a")
        os.makedirs(cand_a)
        with open(os.path.join(cand_a, "main.py"), "w") as f:
            f.write("print('Hello from main')")

        # Setup Candidate B (Breaks contract: app.py)
        cand_b = os.path.join(self.tmp_dir, "cand_b")
        os.makedirs(cand_b)
        with open(os.path.join(cand_b, "app.py"), "w") as f:
            f.write("print('Hello from app')")

        # Setup Verifier (Enforces main.py existence)
        v_contract = os.path.join(self.tmp_dir, "v_contract")
        os.makedirs(v_contract)
        with open(os.path.join(v_contract, "run.sh"), "w") as f:
            f.write("#!/bin/bash\nif [ -f main.py ]; then exit 0; else exit 1; fi")
        os.chmod(os.path.join(v_contract, "run.sh"), 0o755)

        # Verify A passes
        self.assertEqual(await Oracle.run_test(cand_a, v_contract), "PASS")

        # Verify B fails
        self.assertEqual(await Oracle.run_test(cand_b, v_contract), "FAIL")

        # Simulate Convergence: B adopts contract
        shutil.move(os.path.join(cand_b, "app.py"), os.path.join(cand_b, "main.py"))

        # Verify B now passes
        self.assertEqual(await Oracle.run_test(cand_b, v_contract), "PASS")
