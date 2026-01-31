import subprocess
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class Verifier:
    def __init__(self, test_script_path: str, timeout_sec: int = 10):
        self.test_script_path = test_script_path
        self.timeout_sec = timeout_sec

    def execute(self, target_worktree: str) -> Optional[bool]:
        """
        Executes the verifier against the target worktree.
        
        Args:
            target_worktree: Path to the directory containing the candidate code.
            
        Returns:
            True: Test Passed (Exit Code 0)
            False: Test Failed (Exit Code != 0)
            None: Execution Error / Timeout / Undefined
        """
        if not os.path.exists(target_worktree):
            logger.error(f"Worktree not found: {target_worktree}")
            return None

        # Ensure absolute path for the test script
        abs_test_path = os.path.abspath(self.test_script_path)
        if not os.path.exists(abs_test_path):
             logger.error(f"Test script not found: {abs_test_path}")
             return None

        # Command to run: python3 <test_script>
        # We assume the test script imports the candidate code from the CWD (target_worktree)
        # or expects to run IN that directory.
        cmd = ["python3", abs_test_path]

        try:
            # Run the test inside the target worktree
            # Capture output to avoid clutter, maybe log it if needed
            result = subprocess.run(
                cmd,
                cwd=target_worktree,
                timeout=self.timeout_sec,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return True
            else:
                # Log failure details for debugging
                logger.debug(f"Test failed in {target_worktree}: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.warning(f"Test timed out in {target_worktree}")
            return None # Undefined result
        except Exception as e:
            logger.error(f"Verifier execution error: {e}")
            return None
