import argparse
import sys
import logging
import asyncio
import os
import json
import textwrap
import io
import shutil
import difflib
from pydantic import BaseModel, ConfigDict
from typing import List, Dict, Any, Optional, Union

# Try importing from opencode_ai, but fail gracefully if not available (some environments may not need it immediately)
try:
    from opencode_ai import AsyncOpencode
    from opencode_ai.types import Model, Provider
except ImportError:
    class Model(BaseModel):
        pass
    class Provider(BaseModel):
        pass
    AsyncOpencode = None


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


class StrictModel(Model):
    model_config = ConfigDict(extra='ignore')


class StrictProvider(Provider):
    model_config = ConfigDict(extra='ignore')


class TournamentConfig(BaseModel):
    models: List[Union[StrictModel, Model]]
    providers: List[Union[StrictProvider, Provider]]


def setup_logging(log_level_name: str = None) -> logging.Logger:
    """Configures the root logger with the UnbufferedStreamHandler and WrappingFormatter."""
    if not log_level_name:
        log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
        
    log_level = getattr(logging, log_level_name, logging.INFO)
    handler = UnbufferedStreamHandler(sys.stderr)
    formatter = WrappingFormatter(fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s', width=100)
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    root_logger.addHandler(handler)
    return root_logger


async def validate_config_with_api(args, parser):
    """
    Dynamically fetches available models/providers from a temporary local OpenCode API 
    instance to ensure absolute isolation and validation accuracy.
    """
    if not AsyncOpencode:
        parser.error("opencode_ai module is not installed, cannot validate config with API.")

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
        if hasattr(args, 'provider') and args.provider:
            for p_id in args.provider:
                if p_id not in all_providers:
                    close_matches = difflib.get_close_matches(p_id, list(all_providers.keys()))
                    suggestion = f" Did you mean: {', '.join(close_matches)}?" if close_matches else ""
                    parser.error(f"Provider '{p_id}' not found in OpenCode API.{suggestion} Available: {sorted(all_providers.keys())}")
                
                p_obj = all_providers[p_id]
                hydrated_providers.append(p_obj)

        # 2. Hydrate Models
        if hasattr(args, 'model') and args.model:
            for m_str in args.model:
                parts = m_str.split('/')
                target_p = parts[0] if len(parts) > 1 else (args.provider[0] if getattr(args, 'provider', None) else "opencode")
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
