import argparse
import json
import os
import subprocess
import sys
import shutil
import re
import asyncio
import time
import threading
import math
import webbrowser
import logging
from dotenv import load_dotenv

# Setup global logger
logger = logging.getLogger(__name__)

# Load environment variables from .env if it exists
load_dotenv()

# Resolve OPENCODE_API_KEY from host-side auth.json if not in environment
# This allows plumbing it to the Docker container via docker exec -e
if not os.environ.get("OPENCODE_API_KEY"):
    auth_path = os.path.expanduser("~/.local/share/opencode/auth.json")
    if os.path.exists(auth_path):
        try:
            with open(auth_path, "r") as f:
                auth_data = json.load(f)
            if "opencode" in auth_data and "key" in auth_data["opencode"]:
                os.environ["OPENCODE_API_KEY"] = auth_data["opencode"]["key"]
        except Exception as e:
            print(f"Warning: Could not load host-side OPENCODE_API_KEY from {auth_path}: {e}")

from rich.live import Live
from rich.table import Table
from rich.console import Console
from rich import box
from market.orchestrator import Orchestrator, DEFAULT_EXCLUDE_LIST
from market.core.state import MarketState
from market.core import docker

try:
    from datasets import load_dataset
except ImportError:
    print("Please install datasets: pip install datasets")
    sys.exit(1)

console = Console()
status_map = {}
status_lock = threading.Lock()
setup_lock = asyncio.Lock()

def get_patch_from_winner(work_dir, report, state_dict):
    # Reconstruct MarketState and Orchestrator to reuse logic
    state = MarketState.from_json(json.dumps(state_dict))
    orch = Orchestrator(prompt="", n_agents=0, budget=0, state=state)
    
    winner_id = orch.get_winner_id()
    if not winner_id:
        print("No winner found in state.")
        return None
        
    winner_asset = state.assets.get(winner_id)
    code_path = winner_asset.code_path
    if not code_path:
        print(f"No code_path in winner asset.")
        return None
        
    # Map container-side /testbed paths back to the host work_dir
    if code_path.startswith("/testbed"):
        code_path = os.path.join(work_dir, code_path.replace("/testbed", "").lstrip("/"))
        
    if not os.path.exists(code_path):
        print(f"Winner code_path {code_path} not found.")
        return None
    
    max_price = state.get_asset_price(winner_id)
    print(f"Winner identified from state: {winner_id} (Price: {max_price:.1%})")
        
    # Find the "Initial Baseline" commit
    res = subprocess.run(
        ["git", "log", "--grep=Initial Baseline", "--format=%H", "-n", "1"],
        cwd=code_path, capture_output=True, text=True
    )
    baseline_commit = res.stdout.strip()
    if not baseline_commit:
        raise Exception("Fatal: Could not find 'Initial Baseline' commit for diff generation.")

    # Get the patch
    subprocess.run(["git", "add", "."], cwd=code_path, capture_output=True)
    # Remove problem.md and other junk from staging so it's not in the diff
    for file in ["problem.md", "bun.lock", "package.json", "package-lock.json"]:
        subprocess.run(["git", "reset", baseline_commit, file], cwd=code_path, capture_output=True)
    
    diff_res = subprocess.run(["git", "diff", "--cached", baseline_commit], cwd=code_path, capture_output=True, text=True)
    return diff_res.stdout

async def run_market_on_instance(instance, args, semaphore):
    instance_id = instance['instance_id']
    repo = instance['repo']
    base_commit = instance['base_commit']
    problem_statement = instance['problem_statement']

    # Initialize status entry (should already exist from main, but safety first)
    with status_lock:
        if instance_id not in status_map:
            status_map[instance_id] = {
                "status": "Initializing",
                "start_time": time.time(),
                "stages": []
            }

    def update_status(new_status):
        # Truncate to first line for dashboard
        display_status = str(new_status).split('\n')[0]
        with status_lock:
            info = status_map[instance_id]
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

    async with semaphore:
        try:
            update_status("Cloning Repository")
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
            c_stdout, c_stderr = await clone_proc.communicate()
            if clone_proc.returncode != 0:
                update_status(f"Clone Failed (Exit Code: {clone_proc.returncode})")
                logger.error(f"Clone failed for {instance_id} ({repo}):\nSTDOUT: {c_stdout.decode()}\nSTDERR: {c_stderr.decode()}")
                return None

            # Ensure .arenas/ and other critical system dirs are ignored by adding them to git/info/exclude
            exclude_path = os.path.join(work_dir, ".git", "info", "exclude")
            if os.path.exists(os.path.dirname(exclude_path)):
                with open(exclude_path, "a") as f:
                    for ex in DEFAULT_EXCLUDE_LIST:
                        f.write(f"\n{ex}/\n")

            update_status("Checking Out Commit")
            checkout_proc = await asyncio.create_subprocess_exec(
                "git", "checkout", base_commit,
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            co_stdout, co_stderr = await checkout_proc.communicate()
            if checkout_proc.returncode != 0:
                update_status(f"Checkout Failed (Exit Code: {checkout_proc.returncode})")
                logger.error(f"Checkout failed for {instance_id} at {base_commit}:\nSTDOUT: {co_stdout.decode()}\nSTDERR: {co_stderr.decode()}")
                return None            
            # Save problem statement
            problem_path = os.path.join(work_dir, "problem.md")
            with open(problem_path, "w") as f:
                f.write(problem_statement)

            update_status("Resolving Docker Image")
            image_name = docker.get_image_name(instance_id)
            await docker.pull_image(image_name)
            
            update_status("Starting Container")
            # Mount the current LiCode root to /licode
            licode_host_path = os.path.abspath(".")
            opencode_host_path = os.path.expanduser("~/.opencode")
            container_id = await docker.start_container(image_name, work_dir, licode_host_path, opencode_host_path)

            update_status("Bootstrapping Dependencies")
            # 1. Fix Git Ownership (Necessary for cloning mounted volumes)
            git_safe_proc = await asyncio.create_subprocess_exec(
                "docker", "exec", container_id, "git", "config", "--global", "--add", "safe.directory", "*",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            gs_stdout, gs_stderr = await git_safe_proc.communicate()
            if git_safe_proc.returncode != 0:
                update_status(f"Git Ownership Fix Failed (Exit Code: {git_safe_proc.returncode})")
                logger.error(f"Git ownership fix failed for {instance_id}:\nSTDOUT: {gs_stdout.decode()}\nSTDERR: {gs_stderr.decode()}")
                return None

            # 2. Run Comprehensive Setup via Makefile
            update_status("Waiting for Setup Lock")
            async with setup_lock:
                update_status("Running Container Setup (make setup)")
                # Standard path for SWE-bench images plus our expected bun path
                setup_env = "PATH=/root/.bun/bin:/opt/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
                bootstrap_proc = await asyncio.create_subprocess_exec(
                    "docker", "exec", "-w", "/licode", "-e", setup_env,
                    container_id, "make", "setup", "PIP=/opt/miniconda3/bin/pip", "PYTHON=/opt/miniconda3/bin/python3",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await bootstrap_proc.communicate()
                if bootstrap_proc.returncode != 0:
                    update_status(f"Container Setup Failed (Exit Code: {bootstrap_proc.returncode})")
                    logger.error(f"Make setup failed for {instance_id}:\nSTDOUT: {stdout.decode()}\nSTDERR: {stderr.decode()}")
                    return None
                else:
                    logger.info(f"Make setup succeeded for {instance_id}:\nSTDOUT: {stdout.decode()}\nSTDERR: {stderr.decode()}")

            # 3. Verify Environment (Check if opencode is in PATH and functional)
            update_status("Verifying Environment")
            # Explicitly include the path where opencode binary is expected
            full_setup_env = f"PATH=/licode/.opencode/node_modules/.bin:{setup_env}"
            verify_proc = await asyncio.create_subprocess_exec(
                "docker", "exec", "-e", full_setup_env, container_id, "opencode", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            v_stdout, v_stderr = await verify_proc.communicate()
            if verify_proc.returncode != 0:
                update_status(f"Environment Verification Failed (Exit Code: {verify_proc.returncode})")
                logger.error(f"Environment verification failed for {instance_id}:\nSTDOUT: {v_stdout.decode()}\nSTDERR: {v_stderr.decode()}\nUsed PATH: {full_setup_env}")
                return None

            if args.dummy:
                update_status("Dummy Mode: Returning Empty Patch")
                await asyncio.sleep(1)
                res = {
                    "instance_id": instance_id,
                    "model_patch": "",
                    "model_name_or_path": "dummy-test-agent"
                }
                update_status("Complete")
                return res

            update_status("Setting Up Market")
            log_dir = os.path.join(run_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_file_path = os.path.join(log_dir, f"{instance_id}.log")

            market_cmd = [
                "docker", "exec", "-w", "/testbed",
                "-e", "PYTHONPATH=/licode",
                "-e", "PATH=/root/.bun/bin:/licode/.opencode/node_modules/.bin:/licode/node_modules/.bin:/.opencode/bin:/opt/miniconda3/envs/testbed/bin:/opt/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "-e", f"OPENAI_API_KEY={os.environ.get('OPENAI_API_KEY', '')}",
                "-e", f"ANTHROPIC_API_KEY={os.environ.get('ANTHROPIC_API_KEY', '')}",
                "-e", f"GEMINI_API_KEY={os.environ.get('GEMINI_API_KEY', '')}",
                "-e", f"OPENCODE_API_KEY={os.environ.get('OPENCODE_API_KEY', '')}",
                container_id,
                "/opt/miniconda3/bin/python3", "-m", "market.cli", "run",
                "--prompt", f"Fix the bug described in problem.md.",
                "--agents", str(args.agents),
                "--rounds", str(args.rounds),
                "--json-logs"
            ]

            if getattr(args, 'provider', None):
                if isinstance(args.provider, list):
                    market_cmd.extend(["--provider"] + args.provider)
                else:
                    market_cmd.extend(["--provider", args.provider])
            if getattr(args, 'model', None):
                if isinstance(args.model, list):
                    market_cmd.extend(["--model"] + args.model)
                else:
                    market_cmd.extend(["--model", args.model])
            if getattr(args, 'dashboard', False):
                market_cmd.append("--dashboard")
            if getattr(args, 'skip_validation', False):
                market_cmd.append("--skip-validation")
            
            market_cmd.extend([
                "--max-retries", str(args.max_retries),
                "--timeout", str(args.initial_backoff),
                "--max-backoff", str(args.max_backoff)
            ])

            data = None
            try:
                with open(log_file_path, "w") as log_file:
                    process = await asyncio.create_subprocess_exec(
                        *market_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                        limit=1024 * 1024 * 32,
                    )

                    while True:
                        line_bytes = await process.stdout.readline()
                        if not line_bytes:
                            break
                        line = line_bytes.decode('utf-8', errors='replace')
                        log_file.write(line)
                        log_file.flush()
                        
                        if not line.strip():
                            continue
                        try:
                            msg = json.loads(line)
                            if msg.get("type") == "log":
                                text = msg.get("message", "")
                                if text.startswith("Dashboard active at "):
                                    url = text.replace("Dashboard active at ", "").strip()
                                    with status_lock:
                                        status_map[instance_id]["dashboard_url"] = url

                                    # Re-issue the official signal back to the parent terminal.
                                    sys.stderr.write(f"\nDashboard active at {url}\n")
                                    sys.stderr.flush()
                                elif "Starting Round" in text:
                                    update_status(text)
                                elif "Convergence reached" in text:
                                    update_status("Convergence Detected")
                            elif msg.get("type") == "final_result" or ("state" in msg and "report" in msg):
                                data = msg
                        except json.JSONDecodeError:
                            continue

                    await process.wait()
                    if process.returncode != 0:
                        update_status(f"Market Failed (Code {process.returncode})")
                        return None
            except Exception as e:
                update_status(f"Error during market execution: {str(e)}")
                return None

            if not data:
                update_status("Extraction Failed: No Final Output")
                return None

            update_status("Fixing Permissions for Host")
            # Change ownership of /testbed contents back to the host user
            # so the host git can read/write the arena worktrees.
            uid, gid = os.getuid(), os.getgid()
            chown_proc = await asyncio.create_subprocess_exec(
                "docker", "exec", container_id, "chown", "-R", f"{uid}:{gid}", "/testbed",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await chown_proc.communicate()

            update_status("Extracting Patch from Winner")
            # FS ops are quick but we can offload if needed. Git diff is in get_patch_from_winner.
            patch = await asyncio.to_thread(get_patch_from_winner, work_dir, data.get("report", ""), data.get("state", {}))
            if patch is None:
                update_status("Patch Extraction Failed")
                return None

            update_status("Complete")
            return {
                "instance_id": instance_id,
                "model_patch": patch,
                "model_name_or_path": f"opencode-market-a{args.agents}-r{args.rounds}"
            }

        except Exception as e:
            update_status(f"Error: {str(e)}")
            return None
        finally:
            if 'container_id' in locals():
                await docker.stop_container(container_id)

def generate_table():
    table = Table(title="OpenCode Market: SWE-bench Evaluation", box=box.ROUNDED)
    table.add_column("Instance ID", justify="left", style="cyan", no_wrap=True)
    table.add_column("Current Status", style="magenta")
    table.add_column("Elapsed", justify="right", style="green")
    table.add_column("Dashboard", style="blue")
    table.add_column("Timeline", style="white", ratio=1)

    with status_lock:
        for iid, info in sorted(status_map.items()):
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
                dash_url = f"[link={dash_url}]{dash_url}[/link]"
            
            table.add_row(
                iid,
                info["status"],
                f"{total_time:.1f}s",
                dash_url,
                " ⮕ ".join(timeline)
            )
    return table

async def async_main():
    parser = argparse.ArgumentParser(description="Evaluate OpenCode Market on SWE-bench Verified")
    parser.add_argument("--repo", type=str, default="pallets/flask", help="Filter by repo to test a subset (e.g., pallets/flask)")
    parser.add_argument("--task-ids", type=str, help="Comma-separated list of SWE-bench task IDs to evaluate")
    parser.add_argument("--dataset", type=str, default="princeton-nlp/SWE-bench_Verified", help="SWE-bench dataset to use (e.g., princeton-nlp/SWE-bench_Verified, princeton-nlp/SWE-bench_Lite)")
    parser.add_argument("--limit", type=int, default=3, help="Max instances to evaluate")
    parser.add_argument("--agents", type=int, default=3, help="Number of market agents")
    parser.add_argument("--rounds", type=int, default=5, help="Number of market rounds")
    parser.add_argument("--provider", type=str, nargs='+', help="LLM Provider(s)")
    parser.add_argument("--model", type=str, nargs='+', help="LLM Model(s)")
    parser.add_argument("--output", type=str, help="Output JSONL file (defaults to swe_bench_results/<run_id>/predictions.jsonl)")
    parser.add_argument("--dummy", action="store_true", help="Run a dummy evaluation returning empty patches without invoking agents.")
    parser.add_argument("--dashboard", action="store_true", help="Launch and show dashboard URLs for each instance.")
    parser.add_argument("--skip-validation", action="store_true", help="Skip dynamic pre-flight model/provider validation inside the container.")
    parser.add_argument("--parallel", type=int, default=3, help="Number of instances to evaluate in parallel during generation.")
    parser.add_argument("--run-eval", action="store_true", help="Automatically run the SWE-bench evaluation harness after generation.")
    parser.add_argument("--eval-workers", type=int, default=2, help="Number of workers for the evaluation harness (Docker containers).")
    parser.add_argument("--max-retries", type=int, default=2, help="Max retries per round (3 attempts total)")
    parser.add_argument("--initial-backoff", type=float, default=120.0, help="Initial timeout in seconds")
    parser.add_argument("--max-backoff", type=float, default=1000.0, help="Maximum timeout ceiling")
    parser.add_argument("--run-id", type=str, help="Unique identifier for this run. Used for folder naming.")

    args = parser.parse_args()

    # Fail immediately if OPENCODE_API_KEY is not set (and not in dummy mode)
    if not args.dummy and not os.environ.get("OPENCODE_API_KEY"):
        print("\n[ERROR] OPENCODE_API_KEY not found.")
        print("Please set it in your environment, .env file,")
        print("or ensure you are logged in via 'opencode auth login'.\n")
        sys.exit(1)

    if not args.run_id:
        mode = "dummy" if args.dummy else "market"
        args.run_id = f"{mode}_{int(time.time())}"

    if not args.output:
        args.output = f"swe_bench_results/{args.run_id}/predictions.jsonl"

    run_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(run_dir, exist_ok=True)
    
    main_log_path = os.path.join(run_dir, "main.log")
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(main_log_path),
            logging.StreamHandler(sys.stderr)
        ]
    )

    def log_print(msg, style=None):
        if style:
            console.print(msg, style=style)
        else:
            console.print(msg)
        logger.info(msg)

    if os.path.exists(args.output):
        os.remove(args.output)

    log_print(f"Loading {args.dataset} dataset...", style="bold green")
    ds = await asyncio.to_thread(load_dataset, args.dataset, split="test")
    
    if args.task_ids:
        target_ids = set(id.strip() for id in args.task_ids.split(","))
        instances = [i for i in ds if i['instance_id'] in target_ids]
        
        found_ids = set(i['instance_id'] for i in instances)
        missing_ids = target_ids - found_ids
        if missing_ids:
            log_print(f"Warning: {len(missing_ids)} task IDs not found in dataset {args.dataset}: {sorted(list(missing_ids))}", style="bold yellow")
        
        if not instances:
            log_print(f"Error: No matching instances found for the provided task IDs in {args.dataset}.", style="bold red")
            sys.exit(1)
    elif args.repo:
        instances = [i for i in ds if args.repo in i['repo']]
        instances = instances[:args.limit]
    else:
        instances = list(ds)[:args.limit]
        
    log_print(f"Found {len(instances)} instances to evaluate. Running with parallelism {args.parallel}")

    with status_lock:
        for inst in instances:
            iid = inst['instance_id']
            status_map[iid] = {
                "status": "Queued",
                "start_time": time.time(),
                "stages": []
            }

    semaphore = asyncio.Semaphore(args.parallel)
    results = []
    
    with Live(get_renderable=generate_table, refresh_per_second=4) as live:
        tasks = [run_market_on_instance(inst, args, semaphore) for inst in instances]
        
        for coro in asyncio.as_completed(tasks):
            res = await coro
            if res:
                results.append(res)
                with open(args.output, "a") as f:
                    f.write(json.dumps(res) + "\n")
                
    log_print(f"\nDone! Wrote {len(results)} predictions to {args.output}", style="bold green")
    
    if args.run_eval and results:
        log_print(f"\nStarting automatic evaluation...", style="bold blue")
        output_dir = os.path.dirname(os.path.abspath(args.output))
        eval_cmd = [
            sys.executable, "-m", "swebench.harness.run_evaluation",
            "--dataset_name", args.dataset,
            "--predictions_path", os.path.abspath(args.output),
            "--max_workers", str(args.eval_workers),
            "--run_id", args.run_id,
            "--report_dir", ".",
            "--cache_level", "instance",
            "--namespace", "ghcr.io/epoch-research"
        ]
        log_print(f"Executing: {' '.join(eval_cmd)}")
        
        env = os.environ.copy()
        env["FORCE_COLOR"] = "1"
        env["TERM"] = "xterm-256color"
        
        eval_proc = await asyncio.create_subprocess_exec(
            *eval_cmd,
            cwd=output_dir,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        while True:
            line_bytes = await eval_proc.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode('utf-8', errors='replace')
            sys.stdout.write(line)
            sys.stdout.flush()
            logger.info(line.strip())

        await eval_proc.wait()
    else:
        log_print(f"\nTo evaluate manually, run the SWE-bench harness:", style="bold yellow")
        log_print(f"python -m swebench.harness.run_evaluation --dataset_name {args.dataset} --predictions_path {os.path.abspath(args.output)} --max_workers {args.eval_workers} --run_id {args.run_id} --report_dir {os.path.dirname(os.path.abspath(args.output))} --cache_level instance --namespace ghcr.io/epoch-research")

if __name__ == "__main__":
    asyncio.run(async_main())
