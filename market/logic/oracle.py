import os
import shutil
import subprocess
import tempfile
import uuid
from typing import Literal

ResultType = Literal["PASS", "FAIL", "TIMEOUT", "ERROR"]

class Oracle:
    """
    Executes Verifiers (tests) against Candidates (solutions) in isolation.
    """
    
    @staticmethod
    def run_test(candidate_path: str, verifier_path: str, timeout: int = 2) -> ResultType:
        """
        Runs a specific test against a specific candidate.
        
        Args:
            candidate_path: Path to the solution file (e.g., solution.py)
            verifier_path: Path to the test file (e.g., test_cases.py)
            timeout: Max seconds to run
            
        Returns:
            PASS (exit 0), FAIL (exit != 0), TIMEOUT, or ERROR (file missing)
        """
        if not os.path.exists(candidate_path):
            return "ERROR"
        if not os.path.exists(verifier_path):
            return "ERROR"
            
        # Create a unique temp directory for this execution
        # using standard /tmp or OS temp dir
        temp_dir = os.path.join(tempfile.gettempdir(), f"market_run_{uuid.uuid4().hex}")
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # Copy files to temp dir
            # Rename candidate to 'solution.py' so tests can import it consistently
            dest_cand = os.path.join(temp_dir, "solution.py")
            dest_test = os.path.join(temp_dir, "test_run.py")
            
            shutil.copy(candidate_path, dest_cand)
            shutil.copy(verifier_path, dest_test)
            
            # Run the test
            # We run the TEST file, which imports the SOLUTION
            cmd = ["python3", "test_run.py"]
            
            result = subprocess.run(
                cmd,
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                return "PASS"
            else:
                return "FAIL"
                
        except subprocess.TimeoutExpired:
            return "TIMEOUT"
        except Exception as e:
            print(f"Oracle Error: {e}")
            return "ERROR"
        finally:
            # Cleanup
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
