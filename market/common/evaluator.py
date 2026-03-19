import os
import json
import asyncio
import time
import shutil
import logging
import subprocess
import threading
from typing import Dict, List, Optional, Any, Callable, Type
from rich.table import Table
from rich import box

from market.common.orchestrator import BaseOrchestrator
from market.common.workspace import DEFAULT_EXCLUDE_LIST
from market.core import docker

logger = logging.getLogger(__name__)

class StatusManager:
    """
    Manages the status of multiple SWE-bench instances for dashboarding.
    """
    def __init__(self):
        self.status_map = {}
        self.lock = threading.RLock()

    def init_instance(self, instance_id: str):
        with self.lock:
            if instance_id not in self.status_map:
                self.status_map[instance_id] = {
                    "status": "Queued",
                    "start_time": time.time(),
                    "stages": [],
                    "dashboard_url": "N/A"
                }

    def update_status(self, instance_id: str, new_status: str):
        # Truncate to first line for dashboard
        display_status = str(new_status).split('\n')[0]
        with self.lock:
            if instance_id not in self.status_map:
                self.init_instance(instance_id)
            
            info = self.status_map[instance_id]
            now = time.time()
            if info["stages"]:
                last_stage = info["stages"][-1]
                last_stage["duration"] = now - last_stage["start_time"]

            info["status"] = display_status
            info["stages"].append({
                "name": display_status,
                "start_time": now,
                "duration": 0
            })

    def set_dashboard_url(self, instance_id: str, url: str):
        with self.lock:
            if instance_id in self.status_map:
                self.status_map[instance_id]["dashboard_url"] = url

    def generate_table(self, title: str = "OpenCode Market: SWE-bench Evaluation") -> Table:
        table = Table(title=title, box=box.ROUNDED)
        table.add_column("Instance ID", justify="left", style="cyan", no_wrap=True)
        table.add_column("Current Status", style="magenta")
        table.add_column("Elapsed", justify="right", style="green")
        table.add_column("Dashboard", style="blue")
        table.add_column("Timeline", style="white", ratio=1)

        with self.lock:
            for iid, info in sorted(self.status_map.items()):
                now = time.time()
                total_time = now - info["start_time"]
                
                timeline = []
                for stage in info["stages"]:
                    name = stage["name"]
                    name = name.replace("Starting Round", "R")
                    dur = stage["duration"] if stage["duration"] > 0 else (now - stage["start_time"])
                    timeline.append(f"[bold]{name}[/bold]({dur:.1f}s)")
                
                dash_url = info.get("dashboard_url", "N/A")
                if dash_url != "N/A":
                    # Note: link only works in some terminals
                    dash_url = f"[link={dash_url}]{dash_url}[/link]"
                
                table.add_row(
                    iid,
                    info["status"],
                    f"{total_time:.1f}s",
                    dash_url,
                    " ⮕ ".join(timeline)
                )
        return table

def get_patch_from_winner(work_dir: str, orchestrator: BaseOrchestrator) -> Optional[str]:
    """
    Extracts a git patch from the winning candidate's worktree.
    """
    winner_id = orchestrator.get_winner_id()
    if not winner_id:
        logger.error("No winner found.")
        return None
        
    # We need to find the "Initial Baseline" commit to generate a clean patch
    # The worktree dir is managed by the orchestrator
    # We can't easily get the worktree_dir from BaseOrchestrator without more assumptions
    # but we can try to find it in the worktrees_dir
    code_path = os.path.join(orchestrator.worktrees_dir, winner_id)
    if not os.path.exists(code_path):
        # In market orchestrator, IDs are cand_0 while worktree names might be different?
        # Actually in market orchestrator it's cand_0, cand_1...
        # and in ELO it's agent_0_session etc.
        # Let's check if the orchestrator has a way to map ID to path.
        if hasattr(orchestrator, 'candidates') and winner_id in orchestrator.candidates:
            code_path = orchestrator.candidates[winner_id].worktree_dir
        elif hasattr(orchestrator, 'state') and winner_id in orchestrator.state.assets:
            code_path = orchestrator.state.assets[winner_id].code_path
            
    if not os.path.exists(code_path):
        logger.error(f"Winner code_path {code_path} not found.")
        return None

    # Map container-side /testbed paths back to the host work_dir if needed
    if code_path.startswith("/testbed"):
        code_path = os.path.join(work_dir, code_path.replace("/testbed", "").lstrip("/"))

    if not os.path.exists(code_path):
        logger.error(f"Winner code_path {code_path} not found on host.")
        return None

    # Find the "Initial Baseline" commit
    res = subprocess.run(
        ["git", "log", "--grep=Initial Baseline", "--format=%H", "-n", "1"],
        cwd=code_path, capture_output=True, text=True
    )
    baseline_commit = res.stdout.strip()
    if not baseline_commit:
        logger.error("Fatal: Could not find 'Initial Baseline' commit for diff generation.")
        return None

    # Get the patch
    subprocess.run(["git", "add", "."], cwd=code_path, capture_output=True)
    # Remove problem.md and other junk from staging so it's not in the diff
    for file in ["problem.md", "bun.lock", "package.json", "package-lock.json"]:
        subprocess.run(["git", "reset", baseline_commit, file], cwd=code_path, capture_output=True)
    
    diff_res = subprocess.run(["git", "diff", "--cached", baseline_commit], cwd=code_path, capture_output=True, text=True)
    if diff_res.returncode != 0:
        return None
    return diff_res.stdout

class SWEBenchInstanceRunner:
    """
    Handles the execution of a tournament on a single SWE-bench instance.
    """
    def __init__(self, status_mgr: StatusManager, setup_lock: asyncio.Lock):
        self.status_mgr = status_mgr
        self.setup_lock = setup_lock

    async def run_instance(
        self,
        instance: Dict[str, Any],
        args: Any,
        semaphore: asyncio.Semaphore,
        run_tournament_func: Callable[[str, str, str, Any], Any] # (instance_id, work_dir, container_id, args) -> orchestrator
    ) -> Optional[Dict[str, Any]]:
        instance_id = instance['instance_id']
        repo = instance['repo']
        base_commit = instance['base_commit']
        problem_statement = instance['problem_statement']

        self.status_mgr.init_instance(instance_id)
        
        async with semaphore:
            container_id = None
            try:
                self.status_mgr.update_status(instance_id, "Cloning Repository")
                run_dir = os.path.dirname(os.path.abspath(args.output))
                work_dir = os.path.join(run_dir, "workspaces", instance_id)
                if os.path.exists(work_dir):
                    await asyncio.to_thread(shutil.rmtree, work_dir)
                os.makedirs(work_dir, exist_ok=True)

                repo_url = f"https://github.com/{repo}.git"
                clone_proc = await asyncio.create_subprocess_exec(
                    "git", "clone", repo_url, work_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await clone_proc.communicate()
                if clone_proc.returncode != 0:
                    self.status_mgr.update_status(instance_id, "Clone Failed")
                    return None

                # Git exclude
                exclude_path = os.path.join(work_dir, ".git", "info", "exclude")
                if os.path.exists(os.path.dirname(exclude_path)):
                    with open(exclude_path, "a") as f:
                        for ex in DEFAULT_EXCLUDE_LIST:
                            f.write(f"\n{ex}/\n")

                self.status_mgr.update_status(instance_id, "Checking Out Commit")
                checkout_proc = await asyncio.create_subprocess_exec(
                    "git", "checkout", base_commit,
                    cwd=work_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await checkout_proc.communicate()
                if checkout_proc.returncode != 0:
                    self.status_mgr.update_status(instance_id, "Checkout Failed")
                    return None

                problem_path = os.path.join(work_dir, "problem.md")
                with open(problem_path, "w") as f:
                    f.write(problem_statement)

                if getattr(args, 'dummy', False):
                    self.status_mgr.update_status(instance_id, "Dummy Mode")
                    await asyncio.sleep(0.1)
                    return {"instance_id": instance_id, "model_patch": "", "model_name_or_path": "licode-tournament"}

                self.status_mgr.update_status(instance_id, "Resolving Docker Image")
                image_name = docker.get_image_name(instance_id)
                await docker.pull_image(image_name)
                
                self.status_mgr.update_status(instance_id, "Starting Container")
                licode_host_path = os.path.abspath(".")
                opencode_host_path = os.path.expanduser("~/.opencode")
                container_id = await docker.start_container(image_name, work_dir, licode_host_path, opencode_host_path)

                self.status_mgr.update_status(instance_id, "Bootstrapping Dependencies")
                await asyncio.create_subprocess_exec(
                    "docker", "exec", container_id, "git", "config", "--global", "--add", "safe.directory", "*",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )

                async with self.setup_lock:
                    self.status_mgr.update_status(instance_id, "Running Container Setup")
                    setup_env = "PATH=/root/.bun/bin:/opt/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
                    bootstrap_proc = await asyncio.create_subprocess_exec(
                        "docker", "exec", "-w", "/licode", "-e", setup_env,
                        container_id, "make", "setup", "PIP=/opt/miniconda3/bin/pip", "PYTHON=/opt/miniconda3/bin/python3",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    await bootstrap_proc.communicate()
                    if bootstrap_proc.returncode != 0:
                        self.status_mgr.update_status(instance_id, "Setup Failed")
                        return None

                # Tournament Run
                orch = await run_tournament_func(instance_id, work_dir, container_id, args)
                if not orch:
                    self.status_mgr.update_status(instance_id, "Tournament Failed")
                    return None

                self.status_mgr.update_status(instance_id, "Fixing Permissions")
                uid, gid = os.getuid(), os.getgid()
                await asyncio.create_subprocess_exec(
                    "docker", "exec", container_id, "chown", "-R", f"{uid}:{gid}", "/testbed",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )

                self.status_mgr.update_status(instance_id, "Extracting Patch")
                patch = await asyncio.to_thread(get_patch_from_winner, work_dir, orch)
                if patch is None:
                    self.status_mgr.update_status(instance_id, "Patch Extraction Failed")
                    return None

                self.status_mgr.update_status(instance_id, "Complete")
                return {
                    "instance_id": instance_id,
                    "model_patch": patch,
                    "model_name_or_path": f"licode-tournament"
                }

            except Exception as e:
                logger.error(f"Error in run_instance for {instance_id}: {e}")
                self.status_mgr.update_status(instance_id, f"Error: {e}")
                return None
            finally:
                if container_id:
                    await docker.stop_container(container_id)
