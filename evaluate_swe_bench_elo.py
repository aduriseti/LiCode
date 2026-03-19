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

from market.elo.orchestrator import EloOrchestrator
from market.elo.native_tests import NativeTestIdentifier
from market.common.workspace import WorkspaceManager

# Setup global logger for trace logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("elo_tournament_trace.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

async def run_elo_on_instance(instance, args, semaphore):
    instance_id = instance['instance_id']
    async with semaphore:
        logger.info(f"Starting ELO tournament for instance {instance_id}")
        
        # Setup workspace
        work_dir = os.path.join(args.output_dir, instance_id)
        os.makedirs(work_dir, exist_ok=True)
        
        # Initialize Orchestrator
        orch = EloOrchestrator(prompt=instance['problem_statement'], base_dir=work_dir, max_duration=15)
        
        # Identify native tests
        native_entrypoint = NativeTestIdentifier.identify(os.getcwd())
        if native_entrypoint:
            logger.info(f"Identified native test entrypoint: {native_entrypoint}")
            await orch.add_verifier("native_suite", None, native_entrypoint)
        
        # Add candidates (Example: 3 agents)
        for i in range(3):
            await orch.add_candidate(f"agent_{i}", agent_id=f"agent_{i}_session")
        
        # Run tournament
        results = await orch.run_tournament()
        
        logger.info(f"ELO Tournament finished for {instance_id}. Results: {results}")
        
        # Save results
        with open(os.path.join(work_dir, "elo_results.json"), "w") as f:
            json.dump(results, f, indent=2)

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance_id", type=str, help="Specific instance ID to run")
    parser.add_argument("--output_dir", type=str, default="elo_swe_bench_results")
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()

    # Placeholder for loading dataset (simplified for example)
    # In reality, this would use the same logic as evaluate_swe_bench.py
    instances = [{"instance_id": args.instance_id, "problem_statement": "Fix the bug"}] if args.instance_id else []
    
    semaphore = asyncio.Semaphore(args.concurrency)
    tasks = [run_elo_on_instance(inst, args, semaphore) for inst in instances]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
