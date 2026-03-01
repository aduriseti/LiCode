import argparse
import json
import os
import subprocess
import sys
import shutil
import re
import concurrent.futures
import time
import threading
import math
from rich.live import Live
from rich.table import Table
from rich.console import Console
from rich import box
from market.orchestrator import Orchestrator
from market.core.state import MarketState

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
        
    # Get the patch
    subprocess.run(["git", "add", "."], cwd=code_path, capture_output=True)
    # Remove problem.md from staging so it's not in the diff
    subprocess.run(["git", "reset", "problem.md"], cwd=code_path, capture_output=True)
    
    diff_res = subprocess.run(["git", "diff", "--cached", "HEAD"], cwd=code_path, capture_output=True, text=True)
    return diff_res.stdout

def run_market_on_instance(instance, args):
    instance_id = instance['instance_id']
    repo = instance['repo']
    base_commit = instance['base_commit']
    problem_statement = instance['problem_statement']

    # Initialize status entry
    with status_lock:
        status_map[instance_id] = {
            "status": "Initializing",
            "start_time": time.time(),
            "stages": []
        }

    def update_status(new_status):
        with status_lock:
            info = status_map[instance_id]
            # Record previous stage's duration
            now = time.time()
            if info["stages"]:
                # Last stage duration
                last_stage = info["stages"][-1]
                last_stage["duration"] = now - last_stage["start_time"]
            
            # Start new stage
            info["status"] = new_status
            info["stages"].append({
                "name": new_status,
                "start_time": now,
                "duration": 0
            })

    update_status("Cloning Repository")
    work_dir = os.path.abspath(f"./eval_workspaces/{instance_id}")
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir, exist_ok=True)

    try:
        repo_url = f"https://github.com/{repo}.git"
        subprocess.run(["git", "clone", repo_url, work_dir], check=True, capture_output=True)
        update_status("Checking Out Commit")
        subprocess.run(["git", "checkout", base_commit], cwd=work_dir, check=True, capture_output=True)
        
        # Save problem statement
        problem_path = os.path.join(work_dir, "problem.md")
        with open(problem_path, "w") as f:
            f.write(problem_statement)

        if args.dummy:
            update_status("Dummy Mode: Returning Empty Patch")
            time.sleep(1) # simulate brief delay
            res = {
                "instance_id": instance_id,
                "model_patch": "",
                "model_name_or_path": "dummy-test-agent"
            }
            update_status("Complete")
            return res

        update_status("Setting Up Market")
        market_cmd = [
            sys.executable, "-m", "market.cli", "run",
            "--prompt", f"Fix the bug described in problem.md.",
            "--agents", str(args.agents),
            "--rounds", str(args.rounds),
            "--json-logs"
        ]

        if args.provider:
            market_cmd.extend(["--provider", args.provider])
        if args.model:
            market_cmd.extend(["--model", args.model])

        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.abspath(".") 

        # Execute market.cli and monitor stdout
        process = subprocess.Popen(
            market_cmd, 
            cwd=work_dir, 
            env=env, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        data = None
        for line in process.stdout:
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
                if msg.get("type") == "log":
                    text = msg.get("message", "")
                    if "Starting Round" in text:
                        update_status(text)
                    elif "Convergence reached" in text:
                        update_status("Convergence Detected")
                elif msg.get("type") == "final_result":
                    data = msg
            except json.JSONDecodeError:
                continue

        process.wait()
        if process.returncode != 0:
            err = process.stderr.read()
            update_status(f"Market Failed (Code {process.returncode})")
            return None

        if not data:
            update_status("Extraction Failed: No Final Output")
            return None

        update_status("Extracting Patch from Winner")
        patch = get_patch_from_winner(work_dir, data.get("report", ""), data.get("state", {}))
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

def generate_table():
    table = Table(title="OpenCode Market: SWE-bench Evaluation", box=box.ROUNDED)
    table.add_column("Instance ID", justify="left", style="cyan", no_wrap=True)
    table.add_column("Current Status", style="magenta")
    table.add_column("Elapsed", justify="right", style="green")
    table.add_column("Timeline", style="white", ratio=1)

    with status_lock:
        for iid, info in sorted(status_map.items()):
            now = time.time()
            total_time = now - info["start_time"]
            
            # Construct timeline string
            timeline = []
            for stage in info["stages"]:
                name = stage["name"]
                # Abbreviate long round messages
                name = name.replace("Starting Round", "R")
                dur = stage["duration"] if stage["duration"] > 0 else (now - stage["start_time"])
                timeline.append(f"[bold]{name}[/bold]({dur:.1f}s)")
            
            table.add_row(
                iid,
                info["status"],
                f"{total_time:.1f}s",
                " ⮕ ".join(timeline)
            )
    return table

def main():
    parser = argparse.ArgumentParser(description="Evaluate OpenCode Market on SWE-bench Verified")
    parser.add_argument("--repo", type=str, default="pallets/flask", help="Filter by repo to test a subset (e.g., pallets/flask)")
    parser.add_argument("--limit", type=int, default=3, help="Max instances to evaluate")
    parser.add_argument("--agents", type=int, default=3, help="Number of market agents")
    parser.add_argument("--rounds", type=int, default=5, help="Number of market rounds")
    parser.add_argument("--provider", type=str, help="LLM Provider")
    parser.add_argument("--model", type=str, help="LLM Model")
    parser.add_argument("--output", type=str, help="Output JSONL file (defaults to swe_bench_results/<run_id>/predictions.jsonl)")
    parser.add_argument("--dummy", action="store_true", help="Run a dummy evaluation returning empty patches without invoking agents.")
    parser.add_argument("--parallel", type=int, default=3, help="Number of instances to evaluate in parallel during generation.")
    parser.add_argument("--run-eval", action="store_true", help="Automatically run the SWE-bench evaluation harness after generation.")
    parser.add_argument("--eval-workers", type=int, default=2, help="Number of workers for the evaluation harness (Docker containers).")
    parser.add_argument("--run-id", type=str, help="Unique identifier for this run. Used for folder naming.")
    
    args = parser.parse_args()

    # Generate a run_id if not provided
    if not args.run_id:
        mode = "dummy" if args.dummy else "market"
        args.run_id = f"{mode}_{int(time.time())}"

    # Set default output path within the run-specific subfolder
    if not args.output:
        args.output = f"swe_bench_results/{args.run_id}/predictions.jsonl"

    # Ensure output directory exists
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    # Clear output file if it exists to avoid appending to old runs
    if os.path.exists(args.output):
        os.remove(args.output)

    console.print(f"[bold green]Loading SWE-bench Verified dataset...[/bold green]")
    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    
    if args.repo:
        instances = [i for i in ds if args.repo in i['repo']]
    else:
        instances = list(ds)
        
    instances = instances[:args.limit]
    console.print(f"Found {len(instances)} instances to evaluate. Running with parallelism {args.parallel}")

    results = []
    
    with Live(generate_table(), refresh_per_second=4) as live:
        def process_instance(instance):
            res = run_market_on_instance(instance, args)
            live.update(generate_table())
            return res

        with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as executor:
            future_to_instance = {executor.submit(process_instance, inst): inst for inst in instances}
            
            for future in concurrent.futures.as_completed(future_to_instance):
                inst = future_to_instance[future]
                try:
                    res = future.result()
                    if res:
                        results.append(res)
                        with open(args.output, "a") as f:
                            f.write(json.dumps(res) + "\n")
                    live.update(generate_table())
                except Exception as exc:
                    print(f"\n[red]{inst['instance_id']} generated an exception: {exc}[/red]")
                
    console.print(f"\n[bold green]Done! Wrote {len(results)} predictions to {args.output}[/bold green]")
    
    if args.run_eval and results:
        console.print(f"\n[bold blue]Starting automatic evaluation...[/bold blue]")
        output_dir = os.path.dirname(os.path.abspath(args.output))
        eval_cmd = [
            sys.executable, "-m", "swebench.harness.run_evaluation",
            "--dataset_name", "princeton-nlp/SWE-bench_Verified",
            "--predictions_path", os.path.abspath(args.output),
            "--max_workers", str(args.eval_workers),
            "--run_id", args.run_id,
            "--report_dir", "." # Already inside output_dir
        ]
        console.print(f"Executing: {' '.join(eval_cmd)}")
        subprocess.run(eval_cmd, cwd=output_dir)
    else:
        console.print(f"\n[bold yellow]To evaluate manually, run the SWE-bench harness:[/bold yellow]")
        console.print(f"python -m swebench.harness.run_evaluation --dataset_name princeton-nlp/SWE-bench_Verified --predictions_path {os.path.abspath(args.output)} --max_workers {args.eval_workers} --run_id {args.run_id} --report_dir {os.path.dirname(os.path.abspath(args.output))}")

if __name__ == "__main__":
    main()