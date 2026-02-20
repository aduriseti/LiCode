import argparse
import sys
import logging
import asyncio
import os
import json
from market.orchestrator import Orchestrator
from market.runner import MarketRunner

def main():
    parser = argparse.ArgumentParser(description="Logical Induction Market CLI")
    parser.add_argument("--log-level", type=lambda x: x.upper(), default=os.environ.get("LOG_LEVEL", "INFO"), 
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Set logging level (default: INFO or $LOG_LEVEL)")
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # INIT
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--prompt", type=str, required=True)
    init_parser.add_argument("--agents", type=int, default=3)
    init_parser.add_argument("--budget", type=float, default=1000.0)
    
    # RUN (Full Auto)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--prompt", type=str, required=True)
    run_parser.add_argument("--agents", type=int, default=3)
    run_parser.add_argument("--budget", type=float, default=1000.0)
    run_parser.add_argument("--rounds", type=int, default=10)
    run_parser.add_argument("--timeout", type=float, default=300.0, help="Agent response timeout in seconds")
    run_parser.add_argument("--api-url", type=str, default="http://127.0.0.1:4096")
    run_parser.add_argument("--model", type=str, default="gemini-3-flash")
    run_parser.add_argument("--provider", type=str, default="opencode")
    run_parser.add_argument("--json-logs", action="store_true", help="Output JSON logs to stdout instead of TUI")
    
    args = parser.parse_args()

    # Configure Logging
    log_level_name = args.log_level.upper()
    log_level = getattr(logging, log_level_name, logging.ERROR)
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
    
    if args.command == "init":
        orch = Orchestrator(args.prompt, args.agents, args.budget)
        print(orch.state.to_json())
    
    elif args.command == "run":
        runner = MarketRunner(
            args.prompt, 
            args.agents, 
            args.budget, 
            args.api_url, 
            model=args.model, 
            provider=args.provider, 
            agent_timeout=args.timeout
        )
        
        async def run_tournament():
            await runner.initialize(json_logs=args.json_logs)
            await runner.run_loop(args.rounds, stream_ui=not args.json_logs, json_logs=args.json_logs)

        asyncio.run(run_tournament())
        
        # Construct final output
        report = runner.orchestrator.get_final_report()
        output = {
            "state": json.loads(runner.orchestrator.state.to_json()),
            "report": report
        }

        # Dump report to disk for inspection
        try:
            report_path = os.path.join(runner.arena_dir, "TOURNAMENT_REPORT.md")
            with open(report_path, "w") as f:
                f.write(report)
            logging.info(f"Report written to {report_path}")
        except Exception as e:
            logging.warning(f"Failed to write report to disk: {e}")

        if not args.json_logs:
            print(json.dumps(output))

if __name__ == "__main__":
    main()