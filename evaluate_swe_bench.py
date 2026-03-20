import argparse
import json
import os
import subprocess
import sys
import shutil
import asyncio
import time
import logging
from dotenv import load_dotenv

# Setup global logger
logger = logging.getLogger(__name__)

# Load environment variables from .env if it exists
load_dotenv()

# Resolve OPENCODE_API_KEY from host-side auth.json if not in environment
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
from rich.console import Console
from market.orchestrator import Orchestrator
from market.core.state import MarketState
from market.common.evaluator import StatusManager, SWEBenchInstanceRunner, get_patch_from_winner
from market.common.process_registry import registry
from market.core import docker

try:
    from datasets import load_dataset
except ImportError:
    print("Please install datasets: pip install datasets")
    sys.exit(1)

console = Console()
status_mgr = StatusManager()
setup_lock = asyncio.Lock()
runner = SWEBenchInstanceRunner(status_mgr, setup_lock)

async def run_market_tournament(instance_id, work_dir, container_id, args):
    """
    Tournament-specific execution logic for Market.
    """
    log_dir = os.path.join(os.path.dirname(os.path.abspath(args.output)), "logs")
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
        status_mgr.update_status(instance_id, "Setting Up Market")
        with open(log_file_path, "w") as log_file:
            async with registry.spawn(
                *market_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                limit=1024 * 1024 * 32,
            ) as process:

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
                                status_mgr.set_dashboard_url(instance_id, url)
                                sys.stderr.write(f"\nDashboard active at {url}\n")
                                sys.stderr.flush()
                            elif "Starting Round" in text:
                                status_mgr.update_status(instance_id, text)
                            elif "Convergence reached" in text:
                                status_mgr.update_status(instance_id, "Convergence Detected")
                        elif msg.get("type") == "final_result" or ("state" in msg and "report" in msg):
                            data = msg
                    except json.JSONDecodeError:
                        continue

                # The process will be automatically group-killed on exit from the 'async with' block.
                if process.returncode is None:
                    await process.wait()
                    
                if process.returncode != 0:
                    status_mgr.update_status(instance_id, f"Market Failed (Code {process.returncode})")
                    return None
    except Exception as e:
        status_mgr.update_status(instance_id, f"Error: {e}")
        return None

    if not data:
        status_mgr.update_status(instance_id, "No Final Output")
        return None

    # Reconstruct Orchestrator to satisfy get_patch_from_winner
    state = MarketState.from_json(json.dumps(data.get("state", {})))
    orch = Orchestrator(prompt="", n_agents=0, budget=0, state=state)
    return orch

async def async_main():
    parser = argparse.ArgumentParser(description="Evaluate OpenCode Market on SWE-bench Verified")
    parser.add_argument("--repo", type=str, default="pallets/flask", help="Filter by repo to test a subset")
    parser.add_argument("--task-ids", type=str, help="Comma-separated task IDs")
    parser.add_argument("--dataset", type=str, default="princeton-nlp/SWE-bench_Verified", help="Dataset to use")
    parser.add_argument("--limit", type=int, default=3, help="Max instances")
    parser.add_argument("--agents", type=int, default=3, help="Number of market agents")
    parser.add_argument("--rounds", type=int, default=5, help="Number of market rounds")
    parser.add_argument("--provider", type=str, nargs='+', help="LLM Provider(s)")
    parser.add_argument("--model", type=str, nargs='+', help="LLM Model(s)")
    parser.add_argument("--output", type=str, help="Output JSONL file")
    parser.add_argument("--dummy", action="store_true", help="Run dummy evaluation")
    parser.add_argument("--dashboard", action="store_true", help="Launch and show dashboards")
    parser.add_argument("--skip-validation", action="store_true", help="Skip pre-flight validation")
    parser.add_argument("--parallel", type=int, default=3, help="Concurrency")
    parser.add_argument("--run-eval", action="store_true", help="Run evaluation harness after generation")
    parser.add_argument("--eval-workers", type=int, default=2, help="Workers for eval harness")
    parser.add_argument("--max-retries", type=int, default=2, help="Max retries per round")
    parser.add_argument("--initial-backoff", type=float, default=120.0, help="Initial timeout")
    parser.add_argument("--max-backoff", type=float, default=1000.0, help="Max timeout ceiling")
    parser.add_argument("--run-id", type=str, help="Unique identifier for this run")

    args = parser.parse_args()

    if not args.dummy and not os.environ.get("OPENCODE_API_KEY"):
        print("\n[ERROR] OPENCODE_API_KEY not found.\n")
        sys.exit(1)

    if not args.run_id:
        mode = "dummy" if args.dummy else "market"
        args.run_id = f"{mode}_{int(time.time())}"

    if not args.output:
        args.output = f"swe_bench_results/{args.run_id}/predictions.jsonl"

    run_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(run_dir, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(os.path.join(run_dir, "main.log")), logging.StreamHandler(sys.stderr)]
    )

    if os.path.exists(args.output):
        os.remove(args.output)

    logger.info(f"Loading {args.dataset} dataset...")
    ds = await asyncio.to_thread(load_dataset, args.dataset, split="test")
    
    if args.task_ids:
        target_ids = set(id.strip() for id in args.task_ids.split(","))
        instances = [i for i in ds if i['instance_id'] in target_ids]
    elif args.repo:
        instances = [i for i in ds if args.repo in i['repo']][:args.limit]
    else:
        instances = list(ds)[:args.limit]
        
    logger.info(f"Found {len(instances)} instances to evaluate. Running with parallelism {args.parallel}")

    semaphore = asyncio.Semaphore(args.parallel)
    results = []
    
    with Live(get_renderable=status_mgr.generate_table, refresh_per_second=4) as live:
        tasks = [runner.run_instance(inst, args, semaphore, run_market_tournament) for inst in instances]
        
        for coro in asyncio.as_completed(tasks):
            res = await coro
            if res:
                results.append(res)
                with open(args.output, "a") as f:
                    f.write(json.dumps(res) + "\n")
                
    logger.info(f"\nDone! Wrote {len(results)} predictions to {args.output}")
    
    if args.run_eval and results:
        logger.info(f"\nStarting automatic evaluation...")
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
        
        async with registry.spawn(
            *eval_cmd, cwd=output_dir, env={**os.environ, "FORCE_COLOR": "1", "TERM": "xterm-256color"},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        ) as eval_proc:
            while True:
                line_bytes = await eval_proc.stdout.readline()
                if not line_bytes: break
                line = line_bytes.decode('utf-8', errors='replace')
                sys.stdout.write(line)
                sys.stdout.flush()

            if eval_proc.returncode is None:
                await eval_proc.wait()

if __name__ == "__main__":
    asyncio.run(async_main())
