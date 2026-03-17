import os
from pathlib import Path

def pytest_configure(config):
    """
    Configure the test environment before any tests run.
    Prepend the local .opencode/node_modules/.bin to the PATH so that
    subprocesses (like the dashboard) can find 'bun' and other tools.
    """
    # Get project root assuming conftest.py is now in the root
    root_dir = Path(__file__).parent.absolute()
    local_bin = root_dir / ".opencode" / "node_modules" / ".bin"
    
    if local_bin.exists():
        # Prepend to PATH so it takes precedence over system tools
        os.environ["PATH"] = str(local_bin) + os.pathsep + os.environ.get("PATH", "")
