import os
import subprocess
import logging
import asyncio
from typing import Optional, Tuple

class NativeTestIdentifier:
    """
    Identifies and provides entrypoints for native test suites.
    """
    @staticmethod
    def identify(worktree_dir: str) -> Optional[str]:
        """
        Heuristically identifies the test entrypoint.
        """
        # Python
        if os.path.exists(os.path.join(worktree_dir, "pytest.ini")) or \
           os.path.exists(os.path.join(worktree_dir, "conftest.py")):
            return "pytest"
        
        if os.path.exists(os.path.join(worktree_dir, "requirements.txt")):
            try:
                with open(os.path.join(worktree_dir, "requirements.txt"), "r") as f:
                    content = f.read()
                    if "pytest" in content:
                        return "pytest"
            except Exception:
                pass

        # Node.js
        if os.path.exists(os.path.join(worktree_dir, "package.json")):
            try:
                with open(os.path.join(worktree_dir, "package.json"), "r") as f:
                    content = f.read()
                    if "vitest" in content or "jest" in content:
                        return "npm test"
            except Exception:
                pass
        
        # Generic fallback
        if os.path.exists(os.path.join(worktree_dir, "Makefile")):
            return "make test"
            
        return None

    @staticmethod
    async def run_native(worktree_dir: str, entrypoint: str) -> Tuple[bool, str, str]:
        """
        Runs the native test suite.
        """
        proc = await asyncio.create_subprocess_shell(
            entrypoint,
            cwd=worktree_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode == 0, stdout.decode(errors='replace'), stderr.decode(errors='replace')
