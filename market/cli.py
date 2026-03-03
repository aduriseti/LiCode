import argparse
import sys
import logging
import asyncio
import os
import json
import textwrap
import io
from market.orchestrator import Orchestrator
from market.runner import MarketRunner

class WrappingFormatter(logging.Formatter):
    """Wraps log messages to a fixed width for better terminal readability."""
    def __init__(self, fmt=None, datefmt=None, width=100):
        super().__init__(fmt, datefmt)
        self.width = width

    def format(self, record):
        # Format the original message
        original_msg = super().format(record)
        
        # Split header (timestamp/level) from message body if possible
        # Our format is: %(asctime)s - %(levelname)s - %(message)s
        # We try to wrap only the message part if we can find the separator
        parts = original_msg.split(" - ", 2)
        if len(parts) >= 3:
            header = f"{parts[0]} - {parts[1]} - "
            body = parts[2]
            # Wrap the body
            wrapped_body = textwrap.fill(body, width=self.width, subsequent_indent=" " * len(header))
            return f"{header}{wrapped_body}"
        else:
            # Fallback: Wrap the whole line
            return textwrap.fill(original_msg, width=self.width)

class UnbufferedStreamHandler(logging.StreamHandler):
    """Forces raw atomic writes with CRLF to prevent UI line clumping."""
    def emit(self, record):
        try:
            msg = self.format(record)
            # Use CRLF for stronger terminal line-break signal
            data = (msg + "\r\n").encode('utf-8')
            
            if hasattr(self.stream, 'fileno'):
                try:
                    # Raw syscall write is more atomic and bypasses high-level buffering
                    os.write(self.stream.fileno(), data)
                    return
                except (OSError, io.UnsupportedOperation):
                    pass
            
            # Fallback for streams without fileno (like StringIO in tests)
            self.stream.write(msg + "\n")
            self.flush()
        except Exception:
            self.handleError(record)

class MarketArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        """Custom error handler to return structured feedback without TUI corruption."""
        use_json = "--json-logs" in sys.argv
        error_msg = f"CLI Argument Error: {message}"
        if use_json:
            # Clean single-line JSON to stdout for the plugin to parse
            print(json.dumps({"type": "error", "message": error_msg}))
            sys.stdout.flush()
        else:
            # Fallback for manual CLI usage (stderr is safer than stdout for TUI)
            sys.stderr.write(f"{error_msg}\n")
        sys.exit(2)

def main():
    parser = MarketArgumentParser(description="Logical Induction Market CLI")
    parser.add_argument("--log-level", type=lambda x: x.upper(), default=os.environ.get("LOG_LEVEL", "INFO"), 
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Set logging level (default: INFO or $LOG_LEVEL)")
    
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
    run_parser.add_argument("--timeout", type=float, default=300.0, help="Agent response timeout in seconds")
    run_parser.add_argument("--api-url", type=str, default="http://127.0.0.1:4096")
    run_parser.add_argument("--model", type=str, default="gemini-3-flash")
    run_parser.add_argument("--provider", type=str, default="opencode")
    run_parser.add_argument("--json-logs", action="store_true", help="Output JSON logs to stdout instead of TUI")
    run_parser.add_argument("--dashboard", action="store_true", help="Launch and log to the local web dashboard")
    run_parser.add_argument("--log-level", type=lambda x: x.upper(), 
                            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                            help="Set logging level")
    
    args = parser.parse_args()

    # Configure Logging
    # Prioritize subparser arg, then top-level arg, then env
    # Because of how argparse handles shadowing, we may need to check the raw sys.argv 
    # if it's not set in the subparser but was passed as a global.
    log_level_name = None
    if getattr(args, 'log_level', None):
        log_level_name = args.log_level.upper()
    else:
        # Check if --log-level was passed globally (before subcommand)
        for i, arg in enumerate(sys.argv):
            if arg == "--log-level" and i + 1 < len(sys.argv):
                log_level_name = sys.argv[i+1].upper()
                break
    
    if not log_level_name:
        log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
        
    log_level = getattr(logging, log_level_name, logging.ERROR)
    
    # Use custom handler and formatter
    handler = UnbufferedStreamHandler(sys.stderr)
    formatter = WrappingFormatter(fmt='%(asctime)s - %(levelname)s - %(message)s', width=100)
    handler.setFormatter(formatter)
    
    logger = logging.getLogger("market")
    logger.setLevel(log_level)
    # Remove existing handlers to avoid duplicates if re-initialized
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(handler)
    
    # Also set as root for any other libs if needed, but primarily use 'market'
    # logging.getLogger().setLevel(log_level) 
    
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
            agent_timeout=args.timeout,
            dashboard=args.dashboard
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