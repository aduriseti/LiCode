import os
import json
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

from market.common.workspace import WorkspaceManager, DEFAULT_EXCLUDE_LIST
from market.common.oracle import CommonOracle

class BaseOrchestrator(ABC):
    """
    Base class for all tournament orchestrators.
    Handles common directory setup, workspace management, and agent/verifier tracking.
    """
    def __init__(self, prompt: str, base_dir: str, exclude_list: List[str] = DEFAULT_EXCLUDE_LIST):
        self.prompt = prompt
        self.base_dir = base_dir
        self.worktrees_dir = os.path.join(self.base_dir, "worktrees")
        self.verifiers_dir = os.path.join(self.base_dir, "verifiers")
        self.logs_dir = os.path.join(self.base_dir, "logs")
        self.traces_dir = os.path.join(self.base_dir, "traces")
        self.submissions_dir = os.path.join(self.base_dir, "submissions")
        
        # Ensure directories exist
        os.makedirs(self.worktrees_dir, exist_ok=True)
        os.makedirs(self.verifiers_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.traces_dir, exist_ok=True)
        os.makedirs(self.submissions_dir, exist_ok=True)
        
        # Set worktrees_dir to 0o711 so that opencode serve (acting as the agent)
        # can traverse to its assigned directory, while individual directories
        # are locked down with 0o700.
        os.chmod(self.worktrees_dir, 0o711)
        os.chmod(self.verifiers_dir, 0o755)

        self.workspace_mgr = WorkspaceManager(exclude_list=exclude_list)
        self.clone_lock = asyncio.Lock()

    @abstractmethod
    async def initialize(self):
        """Tournament-specific initialization."""
        pass

    @abstractmethod
    async def add_candidate(self, cid: str, **kwargs):
        """Tournament-specific candidate addition."""
        pass

    @abstractmethod
    async def add_verifier(self, vid: str, **kwargs):
        """Tournament-specific verifier addition."""
        pass

    @abstractmethod
    def get_winner_id(self) -> Optional[str]:
        """Returns the ID of the winning candidate."""
        pass

    @abstractmethod
    def get_winner_diff(self) -> str:
        """Returns the diff of the winning candidate."""
        pass
