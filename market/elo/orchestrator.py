import os
import json
import asyncio
import logging
import time
import glicko2
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from market.common.workspace import WorkspaceManager
from market.common.oracle import CommonOracle
from market.elo.native_tests import NativeTestIdentifier

@dataclass
class EloState:
    rating_obj: Any = None
    matches: List[Tuple[float, float, float]] = field(default_factory=list) # (opp_r, opp_rd, score)

@dataclass
class CandidateState:
    id: str
    worktree_dir: str
    elo: EloState = field(default_factory=EloState)
    last_diff: str = ""
    failing_tests: List[str] = field(default_factory=list) # List of verifier IDs

@dataclass
class VerifierState:
    id: str
    patch_content: Optional[str] = None
    entrypoint: Optional[str] = None
    elo: EloState = field(default_factory=EloState) # Verifiers also have ratings

class AgentSession:
    """
    Handles a headless OpenCode session for an agent.
    """
    def __init__(self, agent_id: str, worktree_dir: str, agent_type: str = "candidate"):
        self.agent_id = agent_id
        self.worktree_dir = worktree_dir
        self.agent_type = agent_type
        self.process: Optional[asyncio.subprocess.Process] = None

    async def start(self):
        """Starts the headless session."""
        logging.info(f"Starting session for {self.agent_type} agent {self.agent_id}")
        # Placeholder for starting 'opencode serve'
        pass

    async def interrupt(self, message: str, data: Optional[Dict] = None):
        """
        Interrupts the agent and sends a new message.
        """
        trunc_msg = message[:200] + "..." if len(message) > 200 else message
        logging.info(f"Interrupted agent {self.agent_id} with message: {trunc_msg}")
        
        # Write full data to a specific location for the agent
        if data:
            interrupts_dir = os.path.join(self.worktree_dir, ".interrupts")
            os.makedirs(interrupts_dir, exist_ok=True)
            timestamp = int(time.time() * 1000)
            filename = f"interrupt_{timestamp}.json"
            filepath = os.path.join(interrupts_dir, filename)
            with open(filepath, "w") as f:
                json.dump({"message": message, "data": data}, f, indent=2)
            logging.info(f"Wrote full interrupt data to {filepath}")
        
        # Placeholder for signal-based interruption logic
        pass

class Glicko2Shim:
    def create_rating(self):
        return glicko2.Player()
    def rate_1vsMany(self, rating_obj, matches):
        rating_list = [m[0] for m in matches]
        rd_list = [m[1] for m in matches]
        outcomes = [m[2] for m in matches]
        rating_obj.update_player(rating_list, rd_list, outcomes)
        return rating_obj

class EloOrchestrator:
    def __init__(self, prompt: str, base_dir: str = "/tmp/elo_market", max_duration: int = 180):
        self.prompt = prompt
        self.base_dir = base_dir
        self.worktrees_dir = os.path.join(self.base_dir, "worktrees")
        self.verifiers_dir = os.path.join(self.base_dir, "verifiers")
        self.logs_dir = os.path.join(self.base_dir, "logs")
        
        os.makedirs(self.worktrees_dir, exist_ok=True)
        os.makedirs(self.verifiers_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        
        self.workspace_mgr = WorkspaceManager()
        self.glicko = Glicko2Shim()
        
        self.candidates: Dict[str, CandidateState] = {}
        self.verifiers: Dict[str, VerifierState] = {}
        self.agent_sessions: Dict[str, AgentSession] = {}
        self.event_queue: asyncio.Queue = asyncio.Queue()
        
        self.start_time = time.time()
        self.max_duration = max_duration

    async def initialize(self):
        """Initialize the tournament with baseline and native tests."""
        # 1. Add Empty Candidate (Baseline)
        await self.add_candidate("baseline_empty", is_baseline=True)
        
        # 2. Identify and add Native Test Suite
        native_entrypoint = NativeTestIdentifier.identify(os.getcwd())
        if native_entrypoint:
            logging.info(f"Adding native test suite as verifier: {native_entrypoint}")
            await self.add_verifier("native_suite", None, native_entrypoint)

    async def add_candidate(self, cid: str, is_baseline: bool = False, agent_id: Optional[str] = None, agent_type: str = "candidate"):
        """Adds a new candidate and optionally starts an agent session."""
        worktree_dir = os.path.join(self.worktrees_dir, cid)
        if not os.path.exists(worktree_dir):
            await self.workspace_mgr.clone_workspace(os.getcwd(), worktree_dir)
        
        cand = CandidateState(
            id=cid,
            worktree_dir=worktree_dir,
            last_diff=self.workspace_mgr.get_diff(worktree_dir)
        )
        cand.elo.rating_obj = self.glicko.create_rating()
        self.candidates[cid] = cand
        
        if agent_id:
            session = AgentSession(agent_id, worktree_dir, agent_type=agent_type)
            await session.start()
            self.agent_sessions[agent_id] = session
            
        logging.info(f"Added {agent_type}: {cid} (Agent: {agent_id}, Baseline: {is_baseline})")

    async def add_verifier(self, vid: str, patch_content: Optional[str], entrypoint: str):
        """Adds a new verifier (test) to the tournament."""
        ver = VerifierState(
            id=vid,
            patch_content=patch_content,
            entrypoint=entrypoint
        )
        ver.elo.rating_obj = self.glicko.create_rating()
        self.verifiers[vid] = ver
        logging.info(f"Added verifier: {vid}")

    async def run_match(self, cid: str, vid: str):
        """Executes a single match between a candidate and a verifier."""
        candidate = self.candidates.get(cid)
        verifier = self.verifiers.get(vid)
        if not candidate or not verifier:
            return

        res, stdout, stderr = await CommonOracle.run_test(
            candidate_dir=candidate.worktree_dir,
            patch_content=verifier.patch_content,
            entrypoint=verifier.entrypoint
        )

        if res == "ERROR":
            logging.warning(f"Match {cid} vs {vid} resulted in ERROR. Skipping rating update.")
            return

        score = 0.5 # Default for TIMEOUT
        if res == "PASS":
            score = 1.0
            if vid in candidate.failing_tests:
                candidate.failing_tests.remove(vid)
        elif res == "FAIL":
            score = 0.0
            if vid not in candidate.failing_tests:
                candidate.failing_tests.append(vid)
        
        # Accumulate matches for batch update
        candidate.elo.matches.append((verifier.elo.rating_obj.rating, verifier.elo.rating_obj.rd, score))
        verifier.elo.matches.append((candidate.elo.rating_obj.rating, candidate.elo.rating_obj.rd, 1.0 - score))
        
        logging.info(f"Match {cid} vs {vid}: {res} (Score: {score})")

    async def update_all_ratings(self):
        """Processes all pending matches and updates Glicko-2 ratings."""
        for cid, cand in self.candidates.items():
            if cand.elo.matches:
                cand.elo.rating_obj = self.glicko.rate_1vsMany(cand.elo.rating_obj, cand.elo.matches)
                cand.elo.matches = []
        
        for vid, ver in self.verifiers.items():
            if ver.elo.matches:
                ver.elo.rating_obj = self.glicko.rate_1vsMany(ver.elo.rating_obj, ver.elo.matches)
                ver.elo.matches = []

    async def check_for_updates(self):
        """Polls for file changes in candidate worktrees to trigger updates."""
        for cid, cand in self.candidates.items():
            if cid == "baseline_empty":
                continue
            current_diff = self.workspace_mgr.get_diff(cand.worktree_dir)
            if current_diff != cand.last_diff:
                logging.info(f"Detected update for candidate {cid}")
                diff_changes = current_diff
                cand.last_diff = current_diff
                await self.event_queue.put(('CandidateUpdated', cid, diff_changes))

    async def failure_notification_loop(self):
        """Periodically notifies agents of their easiest failing tests."""
        while time.time() - self.start_time < self.max_duration:
            await asyncio.sleep(60) # Run every 60 seconds
            
            for cid, cand in self.candidates.items():
                if not cand.failing_tests:
                    continue
                
                # Sort failing tests by verifier's ELO rating (easiest/lowest rating first)
                sorted_failing = sorted(
                    cand.failing_tests,
                    key=lambda vid: self.verifiers[vid].elo.rating_obj.rating if vid in self.verifiers else 1500
                )
                
                # Take top k=3 easiest
                k = 3
                top_k = sorted_failing[:k]
                
                # Find the corresponding agent_id if exists
                agent_session = None
                for session in self.agent_sessions.values():
                    if session.worktree_dir == cand.worktree_dir:
                        agent_session = session
                        break
                
                if agent_session:
                    message = f"Your current submission failed tests: {', '.join(top_k)}"
                    data = {"failing_tests": top_k, "logs": "Truncated logs..."}
                    await agent_session.interrupt(message, data)

    async def process_event_queue(self):
        """Processes asynchronous events."""
        while time.time() - self.start_time < self.max_duration:
            try:
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                event_type = event[0]
                
                if event_type == 'CandidateUpdated':
                    cid = event[1]
                    diff_changes = event[2]
                    
                    # 1. Notify rival agents
                    for session in self.agent_sessions.values():
                        if session.worktree_dir != self.candidates[cid].worktree_dir and session.agent_type == "candidate":
                            await session.interrupt(
                                f"Candidate {cid} (a rival) has submitted a new version.",
                                {"diff": diff_changes}
                            )
                    
                    # 2. Schedule matches against all available verifiers
                    for vid in self.verifiers.keys():
                        asyncio.create_task(self.run_match(cid, vid))
                        
            except asyncio.TimeoutError:
                pass

    def get_leaderboard(self) -> List[Dict]:
        """Returns the current leaderboard sorted by ELO rating."""
        sorted_cands = sorted(self.candidates.values(), key=lambda x: x.elo.rating_obj.rating, reverse=True)
        return [
            {
                "id": c.id,
                "rating": c.elo.rating_obj.rating,
                "rd": c.elo.rating_obj.rd,
                "failing": len(c.failing_tests)
            }
            for c in sorted_cands
        ]

    async def run_tournament(self):
        """Main tournament loop."""
        logging.info("Starting ELO Tournament")
        await self.initialize()
        
        # Start background tasks
        tasks = [
            asyncio.create_task(self.failure_notification_loop()),
            asyncio.create_task(self.process_event_queue())
        ]
        
        while time.time() - self.start_time < self.max_duration:
            # Check for updates (simulating file watcher)
            await self.check_for_updates()
            
            # Update ratings from recent matches
            await self.update_all_ratings()
            
            # Log status
            logging.info(f"Leaderboard: {self.get_leaderboard()}")
            
            await asyncio.sleep(5) # Tick
            
        # Cancel background tasks
        for task in tasks:
            task.cancel()
            
        logging.info("Tournament Finished")
        return self.get_leaderboard()
