import argparse
import sys
import logging
import asyncio
import os
import json
from dotenv import load_dotenv

# Load environment variables from .env if it exists
load_dotenv()

from market.orchestrator import Orchestrator
from market.runner import MarketRunner
from market.common.cli_utils import MarketArgumentParser, setup_logging, validate_config_with_api

async def async_main():
    parser = MarketArgumentParser(description="Logical Induction Market CLI")
    parser.add_argument("--log-level", type=lambda x: x.upper(), 
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Set logging level")
    
    # 1. Immediate Logging Configuration
    log_level_name = "INFO"
    for i, arg in enumerate(sys.argv):
        if arg == "--log-level" and i + 1 < len(sys.argv):
            log_level_name = sys.argv[i+1].upper()
            break
            
    setup_logging(log_level_name)

    # 2. Argument Parsing
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # INIT
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--prompt", type=str, required=True)
    init_parser.add_argument("--agents", type=int, default=3)
    init_parser.add_argument("--budget", type=float, default=1000.0)
    init_parser.add_argument("--log-level", type=lambda x: x.upper(), 
                            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                            help="Set logging level")
    
    # RUN (Full Auto)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--prompt", type=str, required=True)
    run_parser.add_argument("--agents", type=int, default=3)
    run_parser.add_argument("--budget", type=float, default=1000.0)
    run_parser.add_argument("--rounds", type=int, default=10)
    run_parser.add_argument("--timeout", type=float, default=120.0, help="Initial agent response timeout in seconds (doubles on each retry)")
    run_parser.add_argument("--max-retries", type=int, default=2, help="Max timeout retries per round (default 2 results in 3 attempts: 2m, 4m, 8m)")
    run_parser.add_argument("--initial-backoff", type=float, default=120.0, help="Deprecated: use --timeout instead")
    run_parser.add_argument("--max-backoff", type=float, default=1000.0, help="Maximum timeout ceiling in seconds")
    run_parser.add_argument("--api-url", type=str, default=os.environ.get("OPENCODE_API_URL"), 
                            help="API URL for the induction engine (defaults to cloud or $OPENCODE_API_URL)")
    run_parser.add_argument("--model", type=str, nargs='+', default=["gemini-3-flash", "claude-sonnet-4-6", "glm-5"])
    run_parser.add_argument("--provider", type=str, nargs='+', default=["opencode"])
    run_parser.add_argument("--json-logs", action="store_true", help="Output JSON logs to stdout instead of TUI")
    run_parser.add_argument("--dashboard", action="store_true", help="Launch and log to the local web dashboard")
    run_parser.add_argument("--skip-validation", action="store_true", help="Skip dynamic pre-flight model/provider validation")
    run_parser.add_argument("--log-level", type=lambda x: x.upper(), 
                            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                            help="Set logging level")
    
    args = parser.parse_args()

    # Flatten potential comma-separated strings in model and provider lists
    if hasattr(args, 'model') and args.model:
        flattened_models = []
        for m in args.model:
            flattened_models.extend([item.strip() for item in m.split(',')])
        args.model = flattened_models
        
    if hasattr(args, 'provider') and args.provider:
        flattened_providers = []
        for p in args.provider:
            flattened_providers.extend([item.strip() for item in p.split(',')])
        args.provider = flattened_providers

    # Dynamic Pre-flight Validation
    if args.command == "run" and not getattr(args, "skip_validation", False):
        try:
            await asyncio.wait_for(validate_config_with_api(args, parser), timeout=120.0)
        except asyncio.TimeoutError:
            parser.error("Pre-flight validation timed out after 120 seconds. The ephemeral OpenCode server failed to respond.")
    
    if args.command == "init":
        orch = Orchestrator(args.prompt, args.agents, args.budget)
        print(orch.state.to_json())
    
    elif args.command == "run":
        async with MarketRunner(
            args.prompt, 
            args.agents, 
            args.budget, 
            args.api_url, 
            model=args.model, 
            provider=args.provider, 
            agent_timeout=args.timeout,
            dashboard=args.dashboard,
            max_retries=args.max_retries,
            initial_backoff=args.initial_backoff,
            max_backoff=args.max_backoff
        ) as runner:
            try:
                await runner.initialize(json_logs=args.json_logs)
                await runner.run_loop(args.rounds, stream_ui=not args.json_logs, json_logs=args.json_logs)
            finally:
                pass # close is called by __aexit__
            
            report = runner.orchestrator.get_final_report()
            output = {
                "state": json.loads(runner.orchestrator.state.to_json()),
                "report": report
            }

        try:
            report_path = os.path.join(runner.arena_dir, "TOURNAMENT_REPORT.md")
            with open(report_path, "w") as f:
                f.write(report)
            logging.info(f"Report written to {report_path}")
        except Exception as e:
            logging.warning(f"Failed to write report to disk: {e}")

        if not args.json_logs:
            print(json.dumps(output))

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()