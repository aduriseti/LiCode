import argparse
import sys
import logging
import asyncio
import os
import json
import time
from dotenv import load_dotenv

# Load environment variables from .env if it exists
load_dotenv()

from market.elo.orchestrator import EloOrchestrator
from market.common.cli_utils import MarketArgumentParser, setup_logging

async def async_main():
    parser = MarketArgumentParser(description="ELO Asynchronous Competition CLI")
    parser.add_argument("--log-level", type=lambda x: x.upper(), 
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Set logging level")
    
    # 1. Immediate Logging Configuration
    log_level_name = "INFO"
    for i, arg in enumerate(sys.argv):
        if arg == "--log-level" and i + 1 < len(sys.argv):
            log_level_name = sys.argv[i+1].upper()
            break
            
    logger = setup_logging(log_level_name)

    # 2. Argument Parsing
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # RUN
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--prompt", type=str, required=True)
    run_parser.add_argument("--agents", type=int, default=4)
    run_parser.add_argument("--max-duration", type=int, default=180, help="Tournament duration in seconds")
    run_parser.add_argument("--output-dir", type=str, default=".arenas", help="Base directory for tournament outputs")
    run_parser.add_argument("--model", type=str, default="gemini-3-flash", help="Model to use")
    run_parser.add_argument("--provider", type=str, default="opencode", help="Provider to use")
    run_parser.add_argument("--log-level", type=lambda x: x.upper(), 
                            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                            help="Set logging level")

    args = parser.parse_args()

    if args.command == "run":
        timestamp = int(time.time())
        run_id = f"elo_run_{timestamp}"
        arena_dir = os.path.join(args.output_dir, run_id)
        os.makedirs(arena_dir, exist_ok=True)
        
        # Add file logging
        logs_dir = os.path.join(arena_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        log_file = os.path.join(logs_dir, "tournament.log")
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(file_handler)
        
        logger.info(f"ELO Tournament Arena initialized at: {arena_dir}")
        
        orch = EloOrchestrator(
            prompt=args.prompt, 
            base_dir=arena_dir, 
            max_duration=args.max_duration,
            model=args.model,
            provider=args.provider
        )
        
        # Add agents with round-robin roles (1:1 ratio)
        for i in range(args.agents):
            agent_id = f"agent_{i}"
            if i % 2 == 1:
                await orch.add_tester(agent_id=agent_id)
            else:
                await orch.add_candidate(agent_id=agent_id)
            
        # Run tournament
        results = await orch.run_tournament()
        
        logger.info(f"Tournament Finished. Leaderboard: {json.dumps(results, indent=2)}")
        
        # Save final results
        with open(os.path.join(arena_dir, "elo_results.json"), "w") as f:
            json.dump(results, f, indent=2)
            
        # Extract and save winning patch
        winning_diff = orch.get_winner_diff()
        if winning_diff:
            patch_path = os.path.join(arena_dir, "submissions", "winning_patch.diff")
            with open(patch_path, "w") as f:
                f.write(winning_diff)
            logger.info(f"Winning patch saved to {patch_path}")

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
