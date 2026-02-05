import os
import shutil
import subprocess
import tempfile
import uuid
from typing import Literal

ResultType = Literal["PASS", "FAIL", "TIMEOUT", "ERROR"]

class Oracle:
    """
    Executes Verifiers (packages) against Candidates (solutions) in isolation.
    """
    
    @staticmethod
    def run_test(candidate_path: str, verifier_dir: str, timeout: int = 5) -> ResultType:
        """
        Runs a verifier package against a candidate.
        
        Args:
            candidate_path: Path to the solution file (e.g., solution.py)
            verifier_dir: Path to the verifier directory containing run.sh
            timeout: Max seconds to run
            
        Returns:
            PASS (exit 0), FAIL (exit != 0), TIMEOUT, or ERROR
        """
        if not os.path.exists(candidate_path):
            return "ERROR"
        if not os.path.isdir(verifier_dir):
            return "ERROR"
            
        run_sh_path = os.path.join(verifier_dir, "run.sh")
        if not os.path.exists(run_sh_path):
            return "ERROR"

        # Create a unique temp directory for this execution
        temp_dir = os.path.join(tempfile.gettempdir(), f"market_exec_{uuid.uuid4().hex}")
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # 1. Copy verifier package contents to temp_dir
            for item in os.listdir(verifier_dir):
                s = os.path.join(verifier_dir, item)
                d = os.path.join(temp_dir, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)
            
            # 2. Copy candidate to 'solution.py' so verifier can find it
            dest_cand = os.path.join(temp_dir, "solution.py")
            shutil.copy(candidate_path, dest_cand)
            
            # 3. Ensure run.sh is executable
            local_run_sh = os.path.join(temp_dir, "run.sh")
            os.chmod(local_run_sh, 0o755)
            
            # 4. Run the verifier
            # The verifier's run.sh is expected to handle execution and exit codes
            cmd = ["./run.sh"]
            
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
            import logging
            logging.error(f"Oracle Execution Error: {e}")
            return "ERROR"
        finally:
            # Cleanup
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)