import os
import shutil
import asyncio
import logging
import subprocess
from typing import List

DEFAULT_EXCLUDE_LIST = [
    ".arenas", 
    ".home", 
    ".opencode",
    ".interrupts",
    "bun.lock", 
    "node_modules",
    "package.json", 
    "package-lock.json",
    "baseline.diff",
    "opencode.db*",
    "*.log",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "elo_swe_bench_results"
]

class WorkspaceManager:
    """
    Handles workspace cloning, snapshotting, and permission management.
    Shared across different tournament implementations.
    """
    def __init__(self, exclude_list: List[str] = DEFAULT_EXCLUDE_LIST):
        self.exclude_list = exclude_list
        self._clone_lock = asyncio.Lock()

    async def clone_workspace(self, src: str, dest_dir: str):
        """Clones a workspace from src to dest_dir with snapshotting and permission fixes."""
        await asyncio.to_thread(os.makedirs, os.path.dirname(dest_dir), exist_ok=True)
        
        def force_rmtree(path):
            import stat
            def remove_readonly(func, path, _):
                try:
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception:
                    pass
            if os.path.exists(path):
                shutil.rmtree(path, onerror=remove_readonly)
                
        await asyncio.to_thread(force_rmtree, dest_dir)
            
        try:
            async with self._clone_lock:
                await self._create_worktree_snapshot(src, dest_dir)
            logging.info(f"Workspace setup complete for {dest_dir}")
        except Exception as e:
            logging.error(f"Workspace initialization failed for {dest_dir}: {e}")
            raise

    async def _create_worktree_snapshot(self, src: str, dest_dir: str):
        """Internal helper to create a git-based snapshot of the workspace."""
        # 0. Ensure dest_dir is clean (with a simple lock if possible, or just be careful)
        # Using a global-ish lock for the class to prevent collisions in tests
        if not hasattr(WorkspaceManager, '_clone_lock'):
            WorkspaceManager._clone_lock = asyncio.Lock()
            
        async with WorkspaceManager._clone_lock:
            if os.path.exists(dest_dir):
                await asyncio.to_thread(shutil.rmtree, dest_dir, ignore_errors=True)
            os.makedirs(os.path.dirname(dest_dir), exist_ok=True)

            # 1. Clean Baseline from Git (Only committed files)
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "1", "--single-branch", "--no-hardlinks", f"file://{src}", dest_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Git clone failed (code {proc.returncode}): {stderr.decode()}")
        
        # 2. Safety: Remove origin to prevent accidental pushes/leaks
        proc = await asyncio.create_subprocess_exec(
            "git", "remote", "remove", "origin",
            cwd=dest_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        
        # 3. Add to git exclude
        def update_git_exclude():
            exclude_path = os.path.join(dest_dir, ".git", "info", "exclude")
            if os.path.exists(exclude_path):
                with open(exclude_path, "a") as f:
                    for item in self.exclude_list:
                        f.write(f"\n{item}\n")
        await asyncio.to_thread(update_git_exclude)
        
        # 4. Overlay Current Work
        exclude_args_tar = " ".join([f'--exclude="{ex}"' for ex in self.exclude_list])
        # Also rigorously exclude .arenas even if not in list
        if ".arenas" not in self.exclude_list:
            exclude_args_tar += ' --exclude=".arenas"'
            
        tar_cmd = f"git ls-files -co --exclude-standard -z | tar -c --null {exclude_args_tar} -T - | tar -x -C \"{dest_dir}\""
        proc = await asyncio.create_subprocess_shell(
            tar_cmd,
            cwd=src,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Tar pipeline failed")

        # 5. Finalize Worktree (Baseline Diff & Shadow Config)
        await self._finalize_worktree(dest_dir)

    async def _finalize_worktree(self, dest_dir: str):
        """Common finalization steps for a worktree."""
        # Stage changes
        proc = await asyncio.create_subprocess_exec(
            "git", "add", "-N", ".",
            cwd=dest_dir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        
        # Create baseline.diff
        with open(os.path.join(dest_dir, "baseline.diff"), "w") as f:
            proc = await asyncio.create_subprocess_exec(
                "git", "diff", "HEAD",
                cwd=dest_dir, stdout=f, stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()

        # Fix permissions
        def fix_permissions():
            for root, dirs, files in os.walk(dest_dir):
                if ".git" in dirs:
                    dirs.remove(".git")
                os.chmod(root, 0o700)
                for f_name in files:
                    if ".git/" in os.path.join(root, f_name): continue
                    os.chmod(os.path.join(root, f_name), 0o600)
        await asyncio.to_thread(fix_permissions)

        # Shadow Git Config
        for key, val in [("user.email", "market@local"), ("user.name", "Market Oracle")]:
            proc = await asyncio.create_subprocess_exec(
                "git", "config", key, val,
                cwd=dest_dir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
        
        # Initial Commit
        for cmd_args in [["add", "."], ["commit", "--allow-empty", "-m", "Initial Baseline"]]:
            proc = await asyncio.create_subprocess_exec(
                "git", *cmd_args,
                cwd=dest_dir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()

    @staticmethod
    def get_diff(worktree_dir: str) -> str:
        """Returns the current git diff of the worktree, including untracked files."""
        try:
            # Stage untracked files as 'intent-to-add' so they show up in diff HEAD
            subprocess.run(["git", "add", "-N", "."], cwd=worktree_dir, capture_output=True)
            return subprocess.check_output(["git", "diff", "HEAD"], cwd=worktree_dir).decode()
        except Exception:
            return ""

    @staticmethod
    async def apply_patch(worktree_dir: str, patch_content: str) -> bool:
        """Applies a git patch to the worktree."""
        proc = await asyncio.create_subprocess_exec(
            "git", "apply", "-",
            cwd=worktree_dir,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate(input=patch_content.encode())
        return proc.returncode == 0
