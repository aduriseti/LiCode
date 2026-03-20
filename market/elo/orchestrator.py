import os
import json
import asyncio
import logging
import time
import glicko2
import sys
import collections
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from market.common.orchestrator import BaseOrchestrator
from market.common.agent import CandidateAgent, TesterAgent, AgentState, InterruptType
from market.common.native_tests import NativeTestIdentifier
from market.common.oracle import CommonOracle, ResultType

@dataclass
class EloState:
    rating_obj: Any = None
    matches: List[Tuple[float, float, float]] = field(default_factory=list) # (opp_r, opp_rd, score)

@dataclass
class CandidateVersion:
    index: int
    diff: str
    elo: EloState = field(default_factory=EloState)
    failing_tests: List[str] = field(default_factory=list) # List of verifier IDs

@dataclass
class CandidateState:
    id: str
    worktree_dir: str
    versions: List[CandidateVersion] = field(default_factory=list)

    @property
    def latest_version(self) -> CandidateVersion:
        return self.versions[-1]

@dataclass
class VerifierState:
    id: str
    patch_content: Optional[str] = None
    entrypoint: Optional[str] = None
    elo: EloState = field(default_factory=EloState) # Verifiers also have ratings

class Glicko2Shim:
    def create_rating(self):
        return glicko2.Player()
    def rate_1vsMany(self, rating_obj, matches):
        rating_list = [m[0] for m in matches]
        rd_list = [m[1] for m in matches]
        outcomes = [m[2] for m in matches]
        rating_obj.update_player(rating_list, rd_list, outcomes)
        return rating_obj

class EloOrchestrator(BaseOrchestrator):
    def __init__(self, prompt: str, base_dir: Optional[str] = None, max_duration: int = 180,
                 model: str = "gemini-3-flash", provider: str = "opencode"):
        if base_dir is None:
            import tempfile
            base_dir = tempfile.mkdtemp(prefix="licode_elo_")
        from market.common.workspace import DEFAULT_EXCLUDE_LIST
        super().__init__(prompt, base_dir, exclude_list=DEFAULT_EXCLUDE_LIST)
        self.model = model
        self.provider = provider
        
        # Isolated match logging directory
        self.match_logs_dir = os.path.join(self.base_dir, "logs", "matches")
        os.makedirs(self.match_logs_dir, exist_ok=True)
        
        self.glicko = Glicko2Shim()
        self.candidates: Dict[str, CandidateState] = {}
        self.verifiers: Dict[str, VerifierState] = {}
        self.agent_sessions: Dict[str, Any] = {}
        self.pending_matches: List[asyncio.Task] = []
        
        # Notification batching & throttling
        self.agent_notification_queues = collections.defaultdict(list)
        self.last_interrupt_times = {} # aid -> timestamp
        
        self.start_time = time.time()
        self.max_duration = max_duration

    def _log_event(self, event_type: str, data: Dict[str, Any]):
        """Logs a structured JSON event for automated verification."""
        event = {
            "timestamp": time.time(),
            "type": event_type,
            "data": data
        }
        # Use a distinctive prefix for easy extraction from logs
        logging.info(f"EVENT_JSON: {json.dumps(event)}")

    async def initialize(self):
        """Initialize the tournament with baseline and native tests."""
        # 1. Add Empty Candidate (Baseline)
        await self.add_candidate(agent_id="baseline_empty", is_baseline=True)
        
        # 2. Identify and add Native Test Suite
        native_entrypoint = NativeTestIdentifier.identify(os.getcwd())
        if native_entrypoint:
            logging.info(f"Adding native test suite as verifier: {native_entrypoint}")
            await self.add_verifier("native_suite", None, native_entrypoint)

    async def add_candidate(self, agent_id: str, is_baseline: bool = False):
        """Adds a new candidate (code producer) and optionally starts an agent session."""
        cid = agent_id
        worktree_dir = os.path.join(self.worktrees_dir, cid)
        
        async with self.clone_lock:
            if not os.path.exists(worktree_dir):
                await self.workspace_mgr.clone_workspace(os.getcwd(), worktree_dir)
        
        initial_diff = self.workspace_mgr.get_diff(worktree_dir)
        
        # Initialize Version 0
        v0 = CandidateVersion(index=0, diff=initial_diff)
        v0.elo.rating_obj = self.glicko.create_rating()
        
        cand = CandidateState(
            id=cid,
            worktree_dir=worktree_dir,
            versions=[v0]
        )
        self.candidates[cid] = cand
        
        self._log_event("candidate_added", {
            "id": cid, 
            "is_baseline": is_baseline,
            "model": self.model,
            "provider": self.provider
        })

        if not is_baseline:
            logging.info(f"Creating candidate agent {agent_id} with model={self.model}, provider={self.provider}")
            session = CandidateAgent(
                agent_id=agent_id, 
                worktree_dir=worktree_dir, 
                model=self.model,
                provider=self.provider,
                traces_dir=self.traces_dir,
                orchestrator=self
            )
            await session.start(initial_prompt=self.prompt)
            self.agent_sessions[agent_id] = session
            
        logging.info(f"Added candidate: {cid} (Baseline: {is_baseline})")

    async def add_tester(self, agent_id: str):
        """Adds a new tester agent (test producer). Testers are NOT candidates themselves."""
        worktree_dir = os.path.join(self.worktrees_dir, agent_id)
        
        async with self.clone_lock:
            if not os.path.exists(worktree_dir):
                await self.workspace_mgr.clone_workspace(os.getcwd(), worktree_dir)
        
        logging.info(f"Creating testing agent {agent_id} with model={self.model}, provider={self.provider}")
        session = TesterAgent(
            agent_id=agent_id, 
            worktree_dir=worktree_dir, 
            model=self.model,
            provider=self.provider,
            traces_dir=self.traces_dir,
            orchestrator=self
        )
        await session.start(initial_prompt=self.prompt)
        self.agent_sessions[agent_id] = session
        
        self._log_event("tester_added", {
            "id": agent_id,
            "model": self.model,
            "provider": self.provider
        })
        logging.info(f"Added tester: {agent_id}")

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
        
        self._log_event("verifier_added", {
            "id": vid,
            "entrypoint": entrypoint
        })
        
        # Save verifier submission to disk
        v_sub_dir = os.path.join(self.submissions_dir, "verifiers")
        os.makedirs(v_sub_dir, exist_ok=True)
        timestamp = int(time.time() * 1000)
        v_file = os.path.join(v_sub_dir, f"{vid}_{timestamp}.json")
        with open(v_file, "w") as f:
            json.dump({
                "id": vid,
                "entrypoint": entrypoint,
                "patch": patch_content,
                "timestamp": timestamp
            }, f, indent=2)
            
        # Schedule matches against all existing candidates for this new test
        for cid, cand in self.candidates.items():
            t = asyncio.create_task(self.run_match(cid, vid, version_idx=len(cand.versions)-1))
            self.pending_matches.append(t)

    async def run_match(self, cid: str, vid: str, version_idx: Optional[int] = None):
        """Executes a single match and logs stdout/stderr to an isolated file."""
        candidate = self.candidates.get(cid)
        verifier = self.verifiers.get(vid)
        if not candidate:
            logging.warning(f"Candidate {cid} not found for match")
            return
        if not verifier:
            logging.warning(f"Verifier {vid} not found for match")
            return

        # Default to latest version if not specified
        if version_idx is None:
            version_idx = len(candidate.versions) - 1
            
        if version_idx >= len(candidate.versions):
            logging.error(f"Invalid version index {version_idx} for candidate {cid}")
            return
            
        version = candidate.versions[version_idx]
        logging.info(f"Running match: {cid} (v{version_idx}) vs {vid}")

        res, stdout, stderr = await CommonOracle.run_test(
            candidate_dir=candidate.worktree_dir,
            patch_content=verifier.patch_content,
            entrypoint=verifier.entrypoint
        )

        # Isolated match logging (Central)
        match_log_file = os.path.join(self.match_logs_dir, f"{cid}_v{version_idx}_vs_{vid}.log")
        # Candidate Worktree logging (Agent visible)
        agent_logs_dir = os.path.join(candidate.worktree_dir, ".test_logs")
        os.makedirs(agent_logs_dir, exist_ok=True)
        agent_log_file = os.path.join(agent_logs_dir, f"v{version_idx}_vs_{vid}.log")
        
        log_content = f"=== MATCH: {cid} (v{version_idx}) vs {vid} ===\n"
        log_content += f"Result: {res}\n"
        log_content += f"\n--- STDOUT ---\n{stdout}\n"
        log_content += f"\n--- STDERR ---\n{stderr}\n"

        for l_file in [match_log_file, agent_log_file]:
            try:
                with open(l_file, "w") as f:
                    f.write(log_content)
            except Exception as e:
                logging.warning(f"Failed to write match log to {l_file}: {e}")

        if res in [ResultType.ERROR, ResultType.PATCH_ERROR]:
            logging.warning(f"Match {cid} (v{version_idx}) vs {vid} resulted in {res}. Skipping rating update.")
            return

        score = 0.0 # Default for FAIL
        if res == ResultType.PASS:
            score = 1.0
            if vid in version.failing_tests:
                version.failing_tests.remove(vid)
        elif res == ResultType.FAIL or res == ResultType.TIMEOUT:
            if vid not in version.failing_tests:
                version.failing_tests.append(vid)
            
            # Queue notification for candidate
            if cid in self.agent_sessions:
                # Truncate stderr/stdout for notification (last 50 lines)
                combined = stderr + "\n" + stdout
                truncated_log = "\n".join(combined.splitlines()[-50:])
                self.agent_notification_queues[cid].append({
                    "type": "failure",
                    "vid": vid,
                    "version": version_idx,
                    "log_path": agent_log_file,
                    "truncated_log": truncated_log
                })

        if res == ResultType.TIMEOUT:
            logging.warning(f"Match {cid} (v{version_idx}) vs {vid} resulted in TIMEOUT. Skipping rating update.")
            return

        # Accumulate matches for batch update
        version.elo.matches.append((verifier.elo.rating_obj.rating, verifier.elo.rating_obj.rd, score))
        verifier.elo.matches.append((version.elo.rating_obj.rating, version.elo.rating_obj.rd, 1.0 - score))
        
        self._log_event("match_completed", {
            "candidate_id": cid,
            "version_index": version_idx,
            "verifier_id": vid,
            "result": res,
            "score": score
        })
        logging.info(f"Match {cid} (v{version_idx}) vs {vid}: {res} (Score: {score})")

    def get_winner_id(self) -> Optional[str]:
        """Returns the ID of the candidate with the highest ELO rating in their LATEST version."""
        eligible = [c for cid, c in self.candidates.items() if cid != "baseline_empty"]
        if not eligible:
            return None
        winner = max(eligible, key=lambda x: x.latest_version.elo.rating_obj.rating)
        return winner.id

    def get_winner_diff(self) -> str:
        """Returns the git diff of the winning candidate's latest version."""
        wid = self.get_winner_id()
        if not wid:
            return ""
        return self.candidates[wid].latest_version.diff

    def get_leaderboard(self) -> Dict[str, List[Dict]]:
        """Returns the current leaderboard sorted by ELO rating for both candidates and verifiers."""
        eligible_cands = [c for cid, c in self.candidates.items() if cid != "baseline_empty"]
        sorted_cands = sorted(eligible_cands, key=lambda x: x.latest_version.elo.rating_obj.rating, reverse=True)
        if "baseline_empty" in self.candidates:
            sorted_cands.append(self.candidates["baseline_empty"])

        sorted_vers = sorted(self.verifiers.values(), key=lambda x: x.elo.rating_obj.rating, reverse=True)

        return {
            "candidates": [
                {
                    "id": c.id,
                    "version": len(c.versions) - 1,
                    "rating": c.latest_version.elo.rating_obj.rating,
                    "rd": c.latest_version.elo.rating_obj.rd,
                    "failing": len(c.latest_version.failing_tests)
                }
                for c in sorted_cands
            ],
            "verifiers": [
                {
                    "id": v.id,
                    "rating": v.elo.rating_obj.rating,
                    "rd": v.elo.rating_obj.rd
                }
                for v in sorted_vers
            ]
        }

    async def update_all_ratings(self):
        """Processes all pending matches and updates Glicko-2 ratings for all versions."""
        for cid, cand in self.candidates.items():
            for i, version in enumerate(cand.versions):
                if version.elo.matches:
                    version.elo.rating_obj = self.glicko.rate_1vsMany(version.elo.rating_obj, version.elo.matches)
                    version.elo.matches = []
                    self._log_event("elo_updated", {
                        "id": cid,
                        "type": "candidate",
                        "version": i,
                        "rating": version.elo.rating_obj.rating,
                        "rd": version.elo.rating_obj.rd
                    })

        for vid, ver in self.verifiers.items():
            if ver.elo.matches:
                ver.elo.rating_obj = self.glicko.rate_1vsMany(ver.elo.rating_obj, ver.elo.matches)
                ver.elo.matches = []
                self._log_event("elo_updated", {
                    "id": vid,
                    "type": "verifier",
                    "rating": ver.elo.rating_obj.rating,
                    "rd": ver.elo.rating_obj.rd
                })

    async def submit_update(self, cid: str, message: str) -> int:
        """
        Manually submits a code update for a candidate.
        Captures the diff, creates a new version, and triggers all matches.
        """
        cand = self.candidates.get(cid)
        if not cand:
            logging.error(f"Cannot submit update: Candidate {cid} not found")
            return -1
            
        current_diff = self.workspace_mgr.get_diff(cand.worktree_dir)
        new_idx = len(cand.versions)
        logging.info(f"Candidate {cid} submitted update: {message}. Creating Version {new_idx}")
        
        # Create New Version
        old_version = cand.latest_version
        new_version = CandidateVersion(
            index=new_idx,
            diff=current_diff,
            failing_tests=list(old_version.failing_tests)
        )
        
        # Inherit Rating but reset RD to default (Episode Reset / Bayesian Prior)
        new_rating = self.glicko.create_rating()
        new_rating.setRating(old_version.elo.rating_obj.rating)
        new_rating.setRd(350.0) # 350 is standard unrated Glicko-2 RD
        new_version.elo.rating_obj = new_rating        
        cand.versions.append(new_version)
        
        self._log_event("update_submitted", {
            "candidate_id": cid,
            "version_index": new_idx,
            "message": message
        })

        # Save candidate update to disk (Central)
        c_sub_dir = os.path.join(self.submissions_dir, "candidates")
        os.makedirs(c_sub_dir, exist_ok=True)
        timestamp = int(time.time() * 1000)
        c_file = os.path.join(c_sub_dir, f"{cid}_v{new_idx}_{timestamp}.diff")
        with open(c_file, "w") as f:
            f.write(current_diff)
        
        # Save diff to Agent Worktree
        agent_diffs_dir = os.path.join(cand.worktree_dir, ".diffs")
        os.makedirs(agent_diffs_dir, exist_ok=True)
        agent_diff_file = os.path.join(agent_diffs_dir, f"v{new_idx}.diff")
        with open(agent_diff_file, "w") as f:
            f.write(current_diff)
            
        # Notify rivals (Queue for batching)
        # Truncate diff for notification
        truncated_diff = "\n".join(current_diff.splitlines()[:50])
        if len(current_diff.splitlines()) > 50:
            truncated_diff += "\n... (truncated, view full diff in your workspace)"

        for rid, session in self.agent_sessions.items():
            if rid == cid: continue
            self.agent_notification_queues[rid].append({
                "type": "rival_update",
                "cid": cid,
                "version": new_idx,
                "truncated_diff": truncated_diff
            })
        
        # REACTIVE: Re-run all verifiers for THIS NEW VERSION
        for vid in self.verifiers.keys():
            t = asyncio.create_task(self.run_match(cid, vid, version_idx=new_idx))
            self.pending_matches.append(t)
            
        return new_idx

    async def check_for_updates(self):
        """Deprecated: Polling is disabled in favor of explicit submit_update."""
        pass

    async def wait_for_matches(self, timeout: float = 30):
        """Waits for all pending matches to complete."""
        if not self.pending_matches:
            return
        
        pending = [t for t in self.pending_matches if not t.done()]
        if pending:
            await asyncio.wait(pending, timeout=timeout)
        self.pending_matches = []

    async def process_notifications(self):
        """Consolidates queued notifications and interrupts agents (with 30s throttle)."""
        now = time.time()
        for aid, queue in list(self.agent_notification_queues.items()):
            if not queue:
                continue
                
            # Throttle: Check if we interrupted this agent recently
            last_time = self.last_interrupt_times.get(aid, 0)
            if now - last_time < 30:
                continue
            
            session = self.agent_sessions.get(aid)
            if not session:
                continue

            # Consolidate messages
            messages = []
            failures = [ev for ev in queue if ev["type"] == "failure"]
            rival_updates = [ev for ev in queue if ev["type"] == "rival_update"]
            
            if failures:
                # Group by version
                f_by_v = collections.defaultdict(list)
                for f in failures: f_by_v[f["version"]].append(f)
                
                for v_idx, v_failures in f_by_v.items():
                    msg = f"Your submission (Version {v_idx}) is failing tests:\n"
                    for f in v_failures[:3]: # Show top 3
                        msg += f"- {f['vid']}\n  Log snippet: {f['truncated_log']}\n  Full log: {f['log_path']}\n"
                    if len(v_failures) > 3:
                        msg += f"... and {len(v_failures) - 3} more.\n"
                    messages.append(msg)
            
            if rival_updates:
                for ru in rival_updates:
                    messages.append(f"Rival {ru['cid']} updated to Version {ru['version']}. Diff snippet:\n{ru['truncated_diff']}")
            
            composite_msg = "\n---\n".join(messages)
            
            # Record interruption BEFORE calling it to avoid re-entry issues if it takes time
            self.last_interrupt_times[aid] = now
            self.agent_notification_queues[aid] = [] # Clear queue
            
            logging.info(f"Interrupting agent {aid} with batched notifications (queue size: {len(queue)})")
            await session.interrupt(
                message=composite_msg,
                data={"type": InterruptType.GENERIC, "events": queue}
            )

    async def shutdown(self):
        """Shut down all agents and cleanup resources."""
        logging.info("EloOrchestrator: Shutting down agents...")
        for session in list(self.agent_sessions.values()):
            try:
                await session.shutdown()
            except Exception as e:
                logging.error(f"Error shutting down agent {session.agent_id}: {e}")
        self.agent_sessions.clear()

    async def run_tournament(self) -> Dict[str, Any]:
        """Main tournament loop."""
        await self.initialize()
        logging.info(f"Tournament started. Max duration: {self.max_duration}s")
        
        try:
            while time.time() - self.start_time < self.max_duration:
                await self.update_all_ratings()
                await self.process_notifications()
                lb = self.get_leaderboard()
                logging.info(f"Leaderboard: {lb}")
                await asyncio.sleep(10) # More frequent checks for batched notifications
                
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()
                
        return {
            "winner_id": self.get_winner_id(),
            "leaderboard": self.get_leaderboard(),
            "duration": time.time() - self.start_time
        }
