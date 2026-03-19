import os
import shutil
import asyncio
import logging
import tempfile
import uuid
import signal
from typing import Literal, Optional, Tuple

ResultType = Literal["PASS", "FAIL", "TIMEOUT", "ERROR"]

class CommonOracle:
    """
    Unified Oracle for executing tests against candidates.
    Shared across different tournament implementations.
    """

    @staticmethod
    def _setup_sandbox_legacy(candidate_dir: str, verifier_dir: str) -> str:
        """Traditional sandbox setup (Copy tree + Overlay verifier)."""
        temp_dir = os.path.join(tempfile.gettempdir(), f"market_exec_{uuid.uuid4().hex}")
        os.makedirs(temp_dir, exist_ok=True)
        
        def ignore_agent_home(path, names):
            return [".home", "__pycache__", ".git"] if any(x in names for x in [".home", "__pycache__", ".git"]) else []
                
        shutil.copytree(candidate_dir, temp_dir, dirs_exist_ok=True, ignore=ignore_agent_home)
        
        for item in os.listdir(verifier_dir):
            s = os.path.join(verifier_dir, item)
            d = os.path.join(temp_dir, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
        
        local_run_sh = os.path.join(temp_dir, "run.sh")
        if os.path.exists(local_run_sh):
            os.chmod(local_run_sh, 0o755)
            
        return temp_dir

    @staticmethod
    async def _setup_sandbox_patch(candidate_dir: str, patch_content: Optional[str]) -> str:
        """New sandbox setup (Copy tree + Apply patch)."""
        temp_dir = os.path.join(tempfile.gettempdir(), f"elo_exec_{uuid.uuid4().hex}")
        os.makedirs(temp_dir, exist_ok=True)
        
        def ignore_agent_home(path, names):
            return [".home", "__pycache__", ".git"] if any(x in names for x in [".home", "__pycache__", ".git"]) else []

        await asyncio.to_thread(shutil.copytree, candidate_dir, temp_dir, dirs_exist_ok=True, ignore=ignore_agent_home)
        
        if patch_content:
            proc = await asyncio.create_subprocess_exec(
                "git", "apply", "-",
                cwd=temp_dir,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate(input=patch_content.encode())
            if proc.returncode != 0:
                logging.error(f"Failed to apply verifier patch: {stderr.decode()}")
                # We still continue, as the test run itself will fail
        
        return temp_dir

    @staticmethod
    async def run_test(
        candidate_dir: str, 
        verifier_dir: Optional[str] = None, 
        patch_content: Optional[str] = None,
        entrypoint: Optional[str] = None
    ) -> Tuple[ResultType, str, str]:
        """
        Runs a test and returns (Result, stdout, stderr).
        """
        temp_dir = None
        try:
            if verifier_dir:
                temp_dir = await asyncio.to_thread(CommonOracle._setup_sandbox_legacy, candidate_dir, verifier_dir)
                cmd = ["./run.sh"]
            elif entrypoint:
                temp_dir = await CommonOracle._setup_sandbox_patch(candidate_dir, patch_content)
                cmd = ["bash", "-c", entrypoint]
            else:
                return "ERROR", "", "No verifier_dir or entrypoint provided"

            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=temp_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True
            )

            stdout, stderr = await process.communicate()
            res_stdout = stdout.decode(errors='replace')
            res_stderr = stderr.decode(errors='replace')
            
            if process.returncode == 0:
                return "PASS", res_stdout, res_stderr
            else:
                return "FAIL", res_stdout, res_stderr
                
        except Exception as e:
            logging.error(f"Oracle Error: {e}")
            return "ERROR", "", str(e)
        finally:
            if temp_dir and os.path.exists(temp_dir):
                await asyncio.to_thread(shutil.rmtree, temp_dir, ignore_errors=True)
