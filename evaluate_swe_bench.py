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
    if not code_path or not os.path.exists(code_path):
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
    # Remove problem.md from staging so it's not in the diff
    subprocess.run(["git", "reset", baseline_commit, "problem.md"], cwd=code_path, capture_output=True)
    
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
        with status_lock:
            info = status_map[instance_id]
            now = time.time()
            if info["stages"]:
                last_stage = info["stages"][-1]
                last_stage["duration"] = now - last_stage["start_time"]
            
            info["status"] = new_status
            info["stages"].append({
                "name": new_status,
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
            await clone_proc.communicate()

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
            await checkout_proc.communicate()
            
            # Save problem statement
            problem_path = os.path.join(work_dir, "problem.md")
            with open(problem_path, "w") as f:
                f.write(problem_statement)

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

            update_status("Resolving Docker Image")
            image_name = docker.get_image_name(instance_id)
            await docker.pull_image(image_name)
            
            update_status("Starting Container")
            # Mount the current LiCode root to /licode
            licode_host_path = os.path.abspath(".")
            container_id = await docker.start_container(image_name, work_dir, licode_host_path)

            update_status("Bootstrapping Dependencies")
            bootstrap_proc = await asyncio.create_subprocess_exec(
                "docker", "exec", container_id, "pip", "install", "-r", "/licode/requirements.txt",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await bootstrap_proc.communicate()

            update_status("Setting Up Market")
            log_dir = os.path.join(run_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_file_path = os.path.join(log_dir, f"{instance_id}.log")

            market_cmd = [
                "docker", "exec", "-w", "/testbed",
                "-e", "PYTHONPATH=/licode",
                "-e", f"OPENAI_API_KEY={os.environ.get('OPENAI_API_KEY', '')}",
                "-e", f"ANTHROPIC_API_KEY={os.environ.get('ANTHROPIC_API_KEY', '')}",
                "-e", f"GEMINI_API_KEY={os.environ.get('GEMINI_API_KEY', '')}",
                container_id,
                "python3", "-m", "market.cli", "run",
                "--prompt", f"Fix the bug described in problem.md.",
                "--agents", str(args.agents),
                "--rounds", str(args.rounds),
                "--json-logs"
            ]

            if getattr(args, 'provider', None):
                market_cmd.extend(["--provider", args.provider])
            if getattr(args, 'model', None):
                market_cmd.extend(["--model", args.model])
            if getattr(args, 'dashboard', False):
                market_cmd.append("--dashboard")
            
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
    parser.add_argument("--provider", type=str, help="LLM Provider")
    parser.add_argument("--model", type=str, help="LLM Model")
    parser.add_argument("--output", type=str, help="Output JSONL file (defaults to swe_bench_results/<run_id>/predictions.jsonl)")
    parser.add_argument("--dummy", action="store_true", help="Run a dummy evaluation returning empty patches without invoking agents.")
    parser.add_argument("--dashboard", action="store_true", help="Launch and show dashboard URLs for each instance.")
    parser.add_argument("--parallel", type=int, default=3, help="Number of instances to evaluate in parallel during generation.")
    parser.add_argument("--run-eval", action="store_true", help="Automatically run the SWE-bench evaluation harness after generation.")
    parser.add_argument("--eval-workers", type=int, default=2, help="Number of workers for the evaluation harness (Docker containers).")
    parser.add_argument("--max-retries", type=int, default=2, help="Max retries per round (3 attempts total)")
    parser.add_argument("--initial-backoff", type=float, default=120.0, help="Initial timeout in seconds")
    parser.add_argument("--max-backoff", type=float, default=1000.0, help="Maximum timeout ceiling")
    parser.add_argument("--run-id", type=str, help="Unique identifier for this run. Used for folder naming.")
    
    args = parser.parse_args()

    if not args.run_id:
        mode = "dummy" if args.dummy else "market"
        args.run_id = f"{mode}_{int(time.time())}"

    if not args.output:
        args.output = f"swe_bench_results/{args.run_id}/predictions.jsonl"

    run_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(run_dir, exist_ok=True)
    
    main_log_path = os.path.join(run_dir, "main.log")
    main_log = open(main_log_path, "a")

    def log_print(msg, style=None):
        if style:
            console.print(msg, style=style)
        else:
            console.print(msg)
        main_log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
        main_log.flush()

    if os.path.exists(args.output):
        os.remove(args.output)

    log_print(f"Loading {args.dataset} dataset...", style="bold green")
    ds = await asyncio.to_thread(load_dataset, args.dataset, split="test")
    
    if args.task_ids:
        target_ids = set(id.strip() for id in args.task_ids.split(","))
        instances = [i for i in ds if i['instance_id'] in target_ids]
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
            "--dataset_name", "princeton-nlp/SWE-bench_Verified",
            "--predictions_path", os.path.abspath(args.output),
            "--max_workers", str(args.eval_workers),
            "--run_id", args.run_id,
            "--report_dir", "."
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
            main_log.write(line)
            main_log.flush()

        await eval_proc.wait()
    else:
        log_print(f"\nTo evaluate manually, run the SWE-bench harness:", style="bold yellow")
        log_print(f"python -m swebench.harness.run_evaluation --dataset_name princeton-nlp/SWE-bench_Verified --predictions_path {os.path.abspath(args.output)} --max_workers {args.eval_workers} --run_id {args.run_id} --report_dir {os.path.dirname(os.path.abspath(args.output))}")

    main_log.close()

if __name__ == "__main__":
    asyncio.run(async_main())
