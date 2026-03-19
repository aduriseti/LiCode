import os
import sys
from pathlib import Path

def _bootstrap():
    """
    Bootstraps the execution environment for the LiCode Market.
    Ensures that project-local binaries are available in the PATH
    for all subsequent subprocess calls.
    """
    # Prevent redundant execution
    if os.environ.get("_LICODE_BOOTSTRAPPED"):
        return

    # Load environment variables globally
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # Clean up API key from environment to prevent literal quotes or whitespace issues
    if "OPENCODE_API_KEY" in os.environ:
        os.environ["OPENCODE_API_KEY"] = os.environ["OPENCODE_API_KEY"].strip("\"' \n\r\t")

    # Resolve project root relative to this file
    # market/ is inside the root
    market_dir = Path(__file__).parent.resolve()
    project_root = market_dir.parent
    
    # Path to local OpenCode binaries
    local_bin = project_root / ".opencode" / "node_modules" / ".bin"
    
    if local_bin.exists():
        # Prepend to PATH so OS-level lookups find our versions first.
        # We also export it to ensure it stays in the environment for child processes.
        os.environ["PATH"] = f"{local_bin}{os.pathsep}{os.environ.get('PATH', '')}"
    
    # Mark as bootstrapped
    os.environ["_LICODE_BOOTSTRAPPED"] = "1"

# Automatically bootstrap on any import from the 'market' package
_bootstrap()
