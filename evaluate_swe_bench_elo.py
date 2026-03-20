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

# Setup global logger for trace logging
logger = logging.getLogger(__name__)

load_dotenv()

from rich.live import Live
from rich.console import Console
from market.elo.orchestrator import EloOrchestrator
from market.common.evaluator import StatusManager, SWEBenchInstanceRunner

try:
    from datasets import load_dataset
except ImportError:
    print("Please install datasets: pip install datasets")
    sys.exit(1)

console = Console()
status_mgr = StatusManager()
setup_lock = asyncio.Lock()
runner = SWEBenchInstanceRunner(status_mgr, setup_lock)

async def run_elo_tournament(instance_id, work_dir, container_id, args):
    """
    Tournament-specific execution logic for ELO.
    """
    status_mgr.update_status(instance_id, "Starting ELO Tournament")
    
    # We run the ELO orchestrator INSIDE the container or OUTSIDE?
    # evaluate_swe_bench.py runs the market CLI INSIDE the container.
    # evaluate_swe_bench_elo.py (original) ran it OUTSIDE.
    # Let's keep it OUTSIDE for now but use the container's mounted work_dir.
    
    # Actually, if we want to support multiple agents with headless servers,
    # running them outside but pointing to the container's volume might be tricky with ports.
    # For now, let's keep the ELO orchestrator running on the host, 
    # but it will use the mounted worktrees.
    
    models = getattr(args, 'model', ["gemini-3-flash"])
    providers = getattr(args, 'provider', ["opencode"])

    orch = EloOrchestrator(
        prompt=f"Fix the bug described in problem.md.",
        base_dir=work_dir,
        max_duration=getattr(args, 'duration', 180),
        model=models,
        provider=providers
    )
    
    # Add agents in pairs (Candidate, Tester per model)
    status_mgr.update_status(instance_id, "Adding Agents")
    n_agents = getattr(args, 'agents', 4) # Default to 4 to ensure at least 2 pairs
    for i in range(n_agents // 2):
        agent_model = models[i % len(models)]
        agent_provider = providers[i % len(providers)]
        
        await orch.add_candidate(
            agent_id=f"agent_{i*2}_cand", 
            model=agent_model, 
            provider=agent_provider
        )
        await orch.add_tester(
            agent_id=f"agent_{i*2+1}_test", 
            model=agent_model, 
            provider=agent_provider
        )
    
    # Run tournament
    # We should probably wrap orch.run_tournament to update status_mgr
    # But for now, we'll just run it.
    status_mgr.update_status(instance_id, "Tournament Running")
    
    # We need a way to poll the orchestrator and update status_mgr
    async def poll_status():
        while True:
            winner = orch.get_winner_id()
            if winner:
                status_mgr.update_status(instance_id, f"Running (Leader: {winner})")
            await asyncio.sleep(10)

    poll_task = asyncio.create_task(poll_status())
    try:
        results = await orch.run_tournament()
    finally:
        poll_task.cancel()
    
    return orch

async def async_main():
    parser = argparse.ArgumentParser(description="Evaluate OpenCode ELO on SWE-bench Verified")
    parser.add_argument("--repo", type=str, help="Filter by repo")
    parser.add_argument("--task-ids", type=str, help="Comma-separated task IDs")
    parser.add_argument("--dataset", type=str, default="princeton-nlp/SWE-bench_Verified", help="Dataset to use")
    parser.add_argument("--limit", type=int, default=3, help="Max instances")
    parser.add_argument("--agents", type=int, default=3, help="Number of agents")
    parser.add_argument("--duration", type=int, default=180, help="Tournament duration in seconds")
    parser.add_argument("--provider", type=str, nargs='+', help="LLM Provider(s)")
    parser.add_argument("--model", type=str, nargs='+', help="LLM Model(s)")
    parser.add_argument("--output", type=str, help="Output JSONL file")
    parser.add_argument("--dummy", action="store_true", help="Run dummy evaluation")
    parser.add_argument("--parallel", type=int, default=1, help="Concurrency")
    parser.add_argument("--run-id", type=str, help="Unique identifier for this run")

    args = parser.parse_args()

    if not args.run_id:
        args.run_id = f"elo_{int(time.time())}"

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
        tasks = [runner.run_instance(inst, args, semaphore, run_elo_tournament) for inst in instances]
        
        for coro in asyncio.as_completed(tasks):
            res = await coro
            if res:
                results.append(res)
                with open(args.output, "a") as f:
                    f.write(json.dumps(res) + "\n")
                
    logger.info(f"\nDone! Wrote {len(results)} predictions to {args.output}")

if __name__ == "__main__":
    asyncio.run(async_main())
