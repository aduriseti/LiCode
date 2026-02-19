import os
import shutil
import subprocess
import tempfile
import uuid
from typing import Literal, Optional

ResultType = Literal["PASS", "FAIL", "TIMEOUT", "ERROR"]

class Oracle:
    """
    Executes Verifiers (packages) against Candidates (solutions) in isolation.
    """
    
    @staticmethod
    def _setup_sandbox(candidate_dir: str, verifier_dir: str) -> Optional[str]:
        """Synchronous helper to setup the test sandbox."""
        temp_dir = os.path.join(tempfile.gettempdir(), f"market_exec_{uuid.uuid4().hex}")
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # 1. Copy ENTIRE candidate worktree to temp_dir
            def ignore_agent_home(path, names):
                return [".home", "__pycache__", ".git"] if any(x in names for x in [".home", "__pycache__", ".git"]) else []
                
            shutil.copytree(candidate_dir, temp_dir, dirs_exist_ok=True, ignore=ignore_agent_home)
            
            # 2. Overlay verifier package contents on top
            for item in os.listdir(verifier_dir):
                s = os.path.join(verifier_dir, item)
                d = os.path.join(temp_dir, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)
            
            # 3. Ensure run.sh is executable
            local_run_sh = os.path.join(temp_dir, "run.sh")
            os.chmod(local_run_sh, 0o755)
            
            return temp_dir
        except Exception as e:
            import logging
            logging.error(f"Oracle Sandbox Setup Error: {e}")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            return None

    @staticmethod
    async def run_test(candidate_dir: str, verifier_dir: str, timeout: int = 15) -> ResultType:
        """
        Runs a verifier package against a candidate worktree.
        
        Args:
            candidate_dir: Path to the candidate's worktree root
            verifier_dir: Path to the verifier directory containing run.sh
            timeout: Max seconds to run
            
        Returns:
            PASS (exit 0), FAIL (exit != 0), TIMEOUT, or ERROR
        """
        import asyncio
        if not os.path.isdir(candidate_dir):
            return "ERROR"
        if not os.path.isdir(verifier_dir):
            return "ERROR"
            
        run_sh_path = os.path.join(verifier_dir, "run.sh")
        if not os.path.exists(run_sh_path):
            return "ERROR"

        # Offload blocking file IO to a thread
        temp_dir = await asyncio.to_thread(Oracle._setup_sandbox, candidate_dir, verifier_dir)
        
        if not temp_dir:
            return "ERROR"
        
        try:
            # 4. Run the verifier
            cmd = ["./run.sh"]
            
            import logging
            logging.info(f"Oracle: Starting test {os.path.basename(verifier_dir)} on worktree {os.path.basename(candidate_dir)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=temp_dir,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
                logging.info(f"Oracle: Finished test {os.path.basename(verifier_dir)} on {os.path.basename(candidate_dir)}")
                
                if process.returncode == 0:
                    return "PASS"
                else:
                    return "FAIL"
            except asyncio.TimeoutError:
                try:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass
                return "TIMEOUT"
                
        except Exception as e:
            import logging
            logging.error(f"Oracle Execution Error: {e}")
            # Ensure process is reaped if it was created
            if 'process' in locals() and process.returncode is None:
                try:
                    process.kill()
                    await process.wait()
                except:
                    pass
            return "ERROR"
        finally:
            # Cleanup (also offloaded to thread to avoid blocking on large deletes)
            if os.path.exists(temp_dir):
                await asyncio.to_thread(shutil.rmtree, temp_dir, ignore_errors=True)