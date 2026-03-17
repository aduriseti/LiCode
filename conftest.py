import os
from pathlib import Path

def pytest_configure(config):
    """
    Configure the test environment before any tests run.
    Environment bootstrapping is now handled automatically by 'import market'.
    """
    pass
