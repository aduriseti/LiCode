import argparse
import sys
import logging
import asyncio
import os
import json
import textwrap
import io
import shutil
from dotenv import load_dotenv

# Load environment variables from .env if it exists
load_dotenv()

# Clean up API key from environment to prevent literal quotes or whitespace issues
if "OPENCODE_API_KEY" in os.environ:
    os.environ["OPENCODE_API_KEY"] = os.environ["OPENCODE_API_KEY"].strip("\"' \n\r\t")

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

from pydantic import BaseModel, ConfigDict
from typing import List, Dict, Any, Optional, Union
from opencode_ai import AsyncOpencode
from opencode_ai.types import Model, Provider
import difflib

class StrictModel(Model):
    model_config = ConfigDict(extra='ignore')

class StrictProvider(Provider):
    model_config = ConfigDict(extra='ignore')

class TournamentConfig(BaseModel):
    models: List[Union[StrictModel, Model]]
    providers: List[Union[StrictProvider, Provider]]

async def validate_config_with_api(args, parser):
    """
    Dynamically fetches available models/providers from a temporary local OpenCode API 
    instance to ensure absolute isolation and validation accuracy.
    """
    import socket
    import time
    
    # 1. Find a free local port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    
    api_url = f"http://127.0.0.1:{port}"
    
    # 2. Spawn ephemeral lookup server
    # We try to use 'opencode' directly if it's in PATH (e.g., from our bootstrap)
    # otherwise we fall back to npx.
    opencode_bin = shutil.which("opencode")
    if opencode_bin:
        cmd_args = [opencode_bin, "serve", "--port", str(port), "--hostname", "127.0.0.1"]
    elif shutil.which("npx"):
        cmd_args = ["npx", "opencode", "serve", "--port", str(port), "--hostname", "127.0.0.1"]
    else:
        raise RuntimeError("Fatal: Neither 'opencode' nor 'npx' found in PATH. Ensure Node.js and the opencode package are installed.")

    process = await asyncio.create_subprocess_exec(
        *cmd_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    try:
        # Wait for server to be ready (poll for up to 10s)
        client = AsyncOpencode(base_url=api_url, timeout=2.0)
        all_providers = {}
        
        start_wait = time.time()
        while (time.time() - start_wait) < 10:
            try:
                res = await client.app.providers()
                if res.providers:
                    all_providers = {p.id: p for p in res.providers}
                    break
            except Exception:
                await asyncio.sleep(0.2)
        
        if not all_providers:
            stdout_text = (await process.stdout.read()).decode()
            stderr_text = (await process.stderr.read()).decode()
            error_msg = f"Failed to initialize ephemeral OpenCode API for validation on port {port}."
            if stdout_text:
                error_msg += f"\nStdout: {stdout_text}"
            if stderr_text:
                error_msg += f"\nStderr: {stderr_text}"
            parser.error(error_msg)

        hydrated_models = []
        hydrated_providers = []

        # 1. Hydrate Providers
        for p_id in args.provider:
            if p_id not in all_providers:
                close_matches = difflib.get_close_matches(p_id, list(all_providers.keys()))
                suggestion = f" Did you mean: {', '.join(close_matches)}?" if close_matches else ""
                parser.error(f"Provider '{p_id}' not found in OpenCode API.{suggestion} Available: {sorted(all_providers.keys())}")
            
            p_obj = all_providers[p_id]
            hydrated_providers.append(p_obj)

        # 2. Hydrate Models
        for m_str in args.model:
            parts = m_str.split('/')
            target_p = parts[0] if len(parts) > 1 else args.provider[0]
            target_m = parts[1] if len(parts) > 1 else m_str

            if target_p not in all_providers:
                 close_matches = difflib.get_close_matches(target_p, list(all_providers.keys()))
                 suggestion = f" Did you mean: {', '.join(close_matches)}?" if close_matches else ""
                 parser.error(f"Model '{m_str}' references unknown provider '{target_p}'.{suggestion} Available: {sorted(all_providers.keys())}")
            
            provider_models = all_providers[target_p].models
            if target_m not in provider_models:
                close_matches = difflib.get_close_matches(target_m, list(provider_models.keys()))
                suggestion = f" Did you mean: {', '.join(close_matches)}?" if close_matches else ""
                parser.error(f"Model '{target_m}' not found for provider '{target_p}'.{suggestion} Available: {sorted(provider_models.keys())}")
            
            m_obj = provider_models[target_m]
            hydrated_models.append(m_obj)

        # 3. Final Pydantic Structural Validation
        try:
            TournamentConfig(models=hydrated_models, providers=hydrated_providers)
        except Exception as e:
            parser.error(f"Configuration structural mismatch with OpenCode schemas: {e}")

    finally:
        # 4. Guaranteed Cleanup of ephemeral server
        if process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except Exception:
                try: process.kill()
                except: pass

async def async_main():
    parser = MarketArgumentParser(description="Logical Induction Market CLI")
    
    # 1. Immediate Logging Configuration
    # We do this FIRST so that even validation errors can be logged if needed,
    # and because the UnbufferedStreamHandler is critical for TUI/Log streaming.
    log_level_name = "INFO"
    for i, arg in enumerate(sys.argv):
        if arg == "--log-level" and i + 1 < len(sys.argv):
            log_level_name = sys.argv[i+1].upper()
            break
    if not log_level_name:
        log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
        
    log_level = getattr(logging, log_level_name, logging.INFO)
    handler = UnbufferedStreamHandler(sys.stderr)
    formatter = WrappingFormatter(fmt='%(asctime)s - %(levelname)s - %(message)s', width=100)
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    root_logger.addHandler(handler)

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
        runner = MarketRunner(
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
        )
        
        try:
            await runner.initialize(json_logs=args.json_logs)
            await runner.run_loop(args.rounds, stream_ui=not args.json_logs, json_logs=args.json_logs)
        finally:
            if not args.dashboard:
                await runner.close()
        
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