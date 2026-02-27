import os
import json
import logging
import time
import hashlib
import shutil
import subprocess
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from market.core.state import MarketState, AgentPortfolio, MarketAsset, MarketBond
from market.core.lmsr import LMSRMarket
from market.core.strategy import Strategy
from market.logic.whale import Whale
from market.logic.oracle import Oracle

@dataclass
class AgentAction:
    agent_id: str
    beliefs: Dict[str, float] = field(default_factory=dict)
    proposals: List[Dict] = field(default_factory=list) # e.g. {"type": "VERIFIER", "path": "..."}

class Orchestrator:
    def __init__(self, prompt: str, n_agents: int, budget: float = 1000.0, state: Optional[MarketState] = None, base_dir: str = "/tmp/market"):
        self.base_dir = base_dir
        self.worktrees_dir = os.path.join(self.base_dir, "worktrees")
        self.verifiers_dir = os.path.join(self.base_dir, "verifiers")
        
        # Ensure directories exist
        os.makedirs(self.worktrees_dir, exist_ok=True)
        os.makedirs(self.verifiers_dir, exist_ok=True)
        
        # Set worktrees_dir to 0o711 so that opencode serve (acting as the agent)
        # can traverse to its assigned directory, while individual directories
        # are locked down with 0o700.
        os.chmod(self.worktrees_dir, 0o711)
        os.chmod(self.verifiers_dir, 0o755)

        self.n_agents = n_agents
        self.budget = budget
        self.prompt = prompt

        if state:
            self.state = state
            self.inference_tax = (0.01 * budget) / n_agents if n_agents > 0 else 1.0
        else:
            self.state = MarketState(
                round_num=0,
                liquidity_b=budget / 20.0, # Initial liquidity
                whale_wealth=budget,
                prompt=prompt
            )
            self.inference_tax = (0.01 * budget) / n_agents if n_agents > 0 else 1.0 # Cost per round
            
        self.bond_lock_period = 1
        self.epsilon = 0.01

    async def initialize(self):
        """Asynchronously initialize the orchestrator and clone workspaces in parallel."""
        import asyncio
        tasks = []
        for i in range(self.n_agents):
            aid = f"agent_{i}"
            if aid not in self.state.agents:
                self.state.agents[aid] = AgentPortfolio(
                    agent_id=aid, 
                    wealth=self.budget / self.n_agents
                )
            # Initialize Candidate for each agent
            cid = f"cand_{i}"
            
            # Create worktree for candidate (Full Clone)
            cand_dir = os.path.join(self.worktrees_dir, cid)
            
            async def setup_cand(c_dir, c_id, a_id):
                # Run blocking shutil in a thread to not block the event loop
                await asyncio.to_thread(self._clone_workspace, c_dir)
                
                # Initial Price: 1/N for candidates (Design 2.B.3)
                import math
                n = self.n_agents
                b = self.state.liquidity_b
                q_no = 0.0
                if n > 1:
                    q_no = b * math.log(n - 1)

                self.state.assets[c_id] = MarketAsset(
                    id=c_id, 
                    type="CANDIDATE", 
                    description=f"Solution by {a_id}",
                    code_path=c_dir, # Point to ROOT of worktree
                    q_no=q_no
                )

            tasks.append(setup_cand(cand_dir, cid, aid))
        
        if tasks:
            await asyncio.gather(*tasks)

    def _clone_workspace(self, dest_dir: str):
        """Clones the project workspace using Hybrid Snapshot Strategy (Clone + Tar Overlay)."""
        src = os.getcwd()
        os.makedirs(os.path.dirname(dest_dir), exist_ok=True)
        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir)
            
        try:
            # 1. Clean Baseline from Git (Only committed files)
            # --no-hardlinks ensures full isolation (safer for untrusted agents)
            logging.info(f"Cloning workspace from {src} to {dest_dir}")
            subprocess.run(["git", "clone", "--local", "--no-hardlinks", src, dest_dir], check=True, capture_output=True)
            
            # 2. Safety: Remove origin
            subprocess.run(["git", "remote", "remove", "origin"], cwd=dest_dir, check=True, capture_output=True)
            
            # 3. Overlay Current Work (Modified + Untracked non-ignored files)
            # Use 'git ls-files -co' to find everything we want to sync
            logging.info(f"Overlaying uncommitted changes to {dest_dir}")
            tar_cmd = f"git ls-files -co --exclude-standard -z | tar -c --null -T - | tar -x -C {dest_dir}"
            subprocess.run(tar_cmd, shell=True, check=True, cwd=src, capture_output=True)

            # Generate baseline.diff for agent context (BEFORE baseline commit)
            # Stage changes to include new files in the diff
            if os.path.exists(dest_dir):
                subprocess.run(["git", "add", "-N", "."], cwd=dest_dir, check=True, capture_output=True)
                with open(os.path.join(dest_dir, "baseline.diff"), "w") as f:
                    subprocess.run(["git", "diff", "HEAD"], cwd=dest_dir, stdout=f, check=True)

                # Fix permissions (git clone/tar might leave them varying)
                # Restrict to 0o700 (owner only) to enforce isolation
                for root, dirs, files in os.walk(dest_dir):
                    # Don't touch .git directory internals as that can break git
                    if ".git" in dirs:
                        dirs.remove(".git")
                    
                    os.chmod(root, 0o700)
                    for f in files:
                        # Skip .git files if walk goes into it (though we removed from dirs)
                        if ".git/" in os.path.join(root, f): continue
                        os.chmod(os.path.join(root, f), 0o600)
            else:
                logging.warning(f"Skipping baseline.diff and permissions: {dest_dir} not found (mocked clone?)")

            # 4. Initialize Shadow Git Config (Needed for baseline commit)
            subprocess.run(["git", "config", "user.email", "market@local"], cwd=dest_dir, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Market Oracle"], cwd=dest_dir, check=True, capture_output=True)
            
            # 5. Commit Baseline (Captures uncommitted work as starting point)
            subprocess.run(["git", "add", "."], cwd=dest_dir, check=True, capture_output=True)
            subprocess.run(["git", "commit", "--allow-empty", "-m", "Initial Baseline"], cwd=dest_dir, check=True, capture_output=True)
            logging.info(f"Workspace setup complete for {dest_dir}")

        except subprocess.CalledProcessError as e:
            logging.error(f"Hybrid Clone failed: {e.stderr.decode() if e.stderr else e}")
            raise

    async def process_round(self, actions: List[AgentAction]):
        """
        Executes one full market round using Simultaneous Batching.
        """
        import asyncio
        self.state.round_num += 1
        logging.info(f"--- Round {self.state.round_num} ---")
        
        # 1. Snapshot State at the very start of the round
        # All decisions (Kelly bets, Whale logic) will be based on this snapshot.
        frozen_state = self.state.clone()
        
        # Track starting wealth for delta logging later
        starting_wealth = {aid: agent.wealth for aid, agent in self.state.agents.items()}
        starting_whale_wealth = self.state.whale_wealth
        
        batch_wagers = [] # List of (trader_id, asset_id, wager)
        
        # Track which assets are new bonds for which agents
        new_bonds_to_create = {} # agent_id -> list of vids
        
        # 2. Process Proposals
        for action in actions:
            agent_id = action.agent_id
            for proposal in action.proposals:
                p_type = proposal.get("type")
                if p_type == "VERIFIER":
                    cid = f"cand_{agent_id.split('_')[-1]}"
                    if cid in self.state.assets:
                        candidate = self.state.assets[cid]
                        source_path = proposal.get("path")
                        if source_path and candidate.code_path:
                            full_source = os.path.join(candidate.code_path, source_path)
                            if os.path.isdir(full_source):
                                # 1. Register verifier (Generates deterministic ID)
                                vid = self._create_verifier_from_path(agent_id, full_source)
                                
                                # 2. Deduplication Check: Only bond if this vid is NEW to the market
                                if vid and vid not in frozen_state.assets:
                                    # Manually mirror to frozen state assets for consistent decision mapping
                                    frozen_state.assets[vid] = self.state.assets[vid]
                                    
                                    logging.info(f"Agent {agent_id} registered NEW verifier: {vid}")
                                    if agent_id not in new_bonds_to_create:
                                        new_bonds_to_create[agent_id] = []
                                    new_bonds_to_create[agent_id].append(vid)
                                elif vid:
                                    logging.debug(f"Agent {agent_id} proposed existing verifier {vid} (skipping redundant bond)")
                            else:
                                logging.warning(f"Agent {agent_id} proposed verifier at non-existent path: {source_path}")

        # 3. Mature Bonds (Active state only; frozen state remains as it was at round start)
        self._mature_bonds()
        
        # 4. Agent Actions (Unified Kelly Bets & Bonds)
        for action in actions:
            agent_id = action.agent_id
            if agent_id not in self.state.agents:
                continue
                
            # Unified Belief Vector: Lump general beliefs + forced bond wagers
            unified_beliefs = action.beliefs.copy()
            
            # Add forced 0.99 belief for all new verifiers proposed by this agent
            vids = new_bonds_to_create.get(agent_id, [])
            for vid in vids:
                unified_beliefs[vid] = 1.0 - self.epsilon
            
            if unified_beliefs:
                # Use ONLY frozen_state for wealth and prices to ensure round-start consistency.
                wagers = Strategy.beliefs_to_wagers(
                    unified_beliefs, 
                    frozen_state.agents[agent_id].wealth, 
                    frozen_state
                )
                for aid, wager in wagers:
                    batch_wagers.append((agent_id, aid, wager))

        # 5. Oracle Execution
        await self._run_oracle()

        # 6. Whale Logic
        # Whale computes target beliefs and wagers using frozen state context.
        whale_wagers = Whale.generate_trades(frozen_state, verifier_prices=None) 
        for aid, wager in whale_wagers:
            batch_wagers.append(("whale", aid, wager))
            
        # 7. Simultaneous Execution (The Clearing Engine)
        # Trades are applied to active self.state
        self._execute_wager_batch(batch_wagers)
        
        # 8. Record Bonds (New bonds are now part of agent.shares)
        for agent_id, vids in new_bonds_to_create.items():
            if agent_id in self.state.agents:
                agent = self.state.agents[agent_id]
                for vid in vids:
                    q_shares = agent.shares.get(vid, 0.0)
                    if q_shares > 0:
                        self.state.bonds.append(MarketBond(
                            agent_id=agent_id,
                            asset_id=vid,
                            q_shares=q_shares,
                            unlock_round=self.state.round_num + self.bond_lock_period
                        ))
                        logging.info(f"Recorded bond for {agent_id} on {vid}: {q_shares:.2f} shares")

        # 9. INSTANT SETTLEMENT
        self._settle_all_bets()

        # 10. Log Round Summary: Prices
        price_summary = {aid: f"{self.state.get_asset_price(aid):.3f}" for aid in self.state.assets}
        logging.info(f"Round {self.state.round_num} Final Prices: {price_summary}")

        # 11. Apply Taxes & Check Bankruptcy
        # An agent is bankrupt if their TOTAL value (Liquid Wealth + Bond Value) <= Tax
        to_remove = []
        for aid, agent in self.state.agents.items():
            # Calculate current market value of all bonds held by this agent
            bond_value = 0.0
            agent_bonds = [b for b in self.state.bonds if b.agent_id == aid]
            for bond in agent_bonds:
                asset = self.state.assets.get(bond.asset_id)
                if asset:
                    price = self.state.get_asset_price(bond.asset_id)
                    bond_value += bond.q_shares * price
            
            total_net_worth = agent.wealth + bond_value
            
            if total_net_worth <= self.inference_tax:
                logging.info(f"Agent {aid} went bankrupt! (Net Worth: {total_net_worth:.2f}, Tax: {self.inference_tax:.2f})")
                to_remove.append(aid)
            else:
                agent.wealth -= self.inference_tax
                
            # Log Wealth and Delta for this agent
            start_w = starting_wealth.get(aid, 0.0)
            delta = agent.wealth - start_w
            logging.info(f"Agent {aid} Wealth: {agent.wealth:.2f} (Net Worth: {total_net_worth:.2f}, Delta: {delta:+.2f})")
                
        # Log Whale Wealth and Delta
        whale_delta = self.state.whale_wealth - starting_whale_wealth
        logging.info(f"Whale Wealth: {self.state.whale_wealth:.2f} (Delta: {whale_delta:+.2f})")

        for aid in to_remove:
            agent = self.state.agents[aid]
            agent_bonds = [b for b in self.state.bonds if b.agent_id == aid]
            for bond in agent_bonds:
                self._liquidate_shares(aid, bond.asset_id, bond.q_shares)
                self.state.bonds.remove(bond)
            
            if abs(agent.wealth) > 0.0001:
                logging.info(f"Agent {aid} estate of {agent.wealth:.2f} escheated to Whale.")
                self.state.whale_wealth += agent.wealth
                agent.wealth = 0.0
                
            del self.state.agents[aid]

    def _liquidate_shares(self, agent_id: str, asset_id: str, q_shares: float):
        """Sells shares back to the LMSR pool and credits the agent."""
        if agent_id not in self.state.agents: return
        agent = self.state.agents[agent_id]
        if asset_id not in self.state.assets: return
        asset = self.state.assets[asset_id]
        b = self.state.liquidity_b
        
        payout = LMSRMarket.calculate_payout(q_shares, asset.q_yes, asset.q_no, b)
        
        if q_shares > 0:
            asset.q_yes -= q_shares
        else:
            asset.q_no += q_shares
            
        agent.wealth += payout
        self.state.whale_wealth -= payout
        
        current_shares = agent.shares.get(asset_id, 0.0)
        new_shares = current_shares - q_shares
        if abs(new_shares) < 1e-5:
            if asset_id in agent.shares: del agent.shares[asset_id]
        else:
            agent.shares[asset_id] = new_shares
            
        logging.info(f"Liquidated {q_shares:.2f} of {asset_id} for {agent_id}. Payout: {payout:.2f}")

    def _settle_all_bets(self):
        """
        Mark-to-Market all belief-based trades.
        Shares not locked in bonds are settled: agents get their current value,
        and the Whale absorbs the position to preserve price discovery.
        """
        locked_shares = {}
        for bond in self.state.bonds:
            if bond.agent_id not in locked_shares:
                locked_shares[bond.agent_id] = {}
            locked_shares[bond.agent_id][bond.asset_id] = locked_shares[bond.agent_id].get(bond.asset_id, 0.0) + bond.q_shares

        for aid, agent in list(self.state.agents.items()):
            for asset_id, q_shares in list(agent.shares.items()):
                locked = locked_shares.get(aid, {}).get(asset_id, 0.0)
                exposure = q_shares - locked
                
                if abs(exposure) > 0.0001:
                    asset = self.state.assets[asset_id]
                    # Calculate fair payout value without moving the price
                    payout = LMSRMarket.calculate_payout(
                        exposure, 
                        asset.q_yes, 
                        asset.q_no, 
                        self.state.liquidity_b
                    )
                    
                    # TRANSFER VALUE: Whale pays Agent
                    agent.wealth += payout
                    self.state.whale_wealth -= payout
                    
                    # Whale absorbs the shares to maintain the market price
                    self.state.whale_shares[asset_id] = self.state.whale_shares.get(asset_id, 0.0) + exposure
                    
                    # Clear the exposure from agent
                    if abs(locked) < 0.0001:
                        del agent.shares[asset_id]
                    else:
                        agent.shares[asset_id] = locked
                    
                    if abs(payout) > 0.0001:
                        logging.info(f"Settlement: Agent {aid} received {payout:.2f} payout for {asset_id} position ({exposure:.2f} shares)")

        # Whale's active trades are kept as part of the market, they aren't settled here.
                
    def _execute_wager_batch(self, intents: List[Tuple[str, str, float]]):
        """
        Clears all intended wagers simultaneously for each asset.
        """
        # Group by asset
        asset_intents = {}
        for trader_id, asset_id, wager in intents:
            if asset_id not in asset_intents:
                asset_intents[asset_id] = []
            asset_intents[asset_id].append((trader_id, wager))
            
        b = self.state.liquidity_b
        
        for asset_id, trades in asset_intents.items():
            if asset_id not in self.state.assets: continue
            asset = self.state.assets[asset_id]
            p0 = self.state.get_asset_price(asset_id)
            
            w_yes = 0.0
            w_no = 0.0
            
            for _, wager in trades:
                if wager > 0: w_yes += wager
                elif wager < 0: w_no += abs(wager)
                
            if w_yes == 0 and w_no == 0: continue
            
            # 1. Matching (Cancel opposing wagers at current price)
            p_yes_safe = max(1e-9, min(1.0 - 1e-9, p0))
            p_no_safe = 1.0 - p_yes_safe
            
            q_match = min(w_yes / p_yes_safe, w_no / p_no_safe)
            
            match_w_yes = q_match * p_yes_safe
            match_w_no = q_match * p_no_safe
            
            rem_w_yes = w_yes - match_w_yes
            rem_w_no = w_no - match_w_no
            
            # 2. Push LMSR with remainder
            delta_q_lmsr_yes = 0.0
            delta_q_lmsr_no = 0.0
            
            if rem_w_yes > 1e-5:
                delta_q_lmsr_yes = LMSRMarket.calculate_delta_q(asset.q_yes, asset.q_no, b, rem_w_yes, True)
                asset.q_yes += delta_q_lmsr_yes
            elif rem_w_no > 1e-5:
                delta_q_lmsr_no = LMSRMarket.calculate_delta_q(asset.q_yes, asset.q_no, b, rem_w_no, False)
                asset.q_no += delta_q_lmsr_no
                
            total_yes_created = q_match + delta_q_lmsr_yes
            total_no_created = q_match + delta_q_lmsr_no
            
            # 3. Distribute Shares & Deduct Wealth
            for trader_id, wager in trades:
                if abs(wager) < 1e-5: continue
                
                # Wealth transfer: Agents pay the pool (Whale)
                if trader_id != "whale":
                    trader_obj = self.state.agents.get(trader_id)
                    if trader_obj:
                        trader_obj.wealth -= abs(wager)
                        self.state.whale_wealth += abs(wager)
                
                if wager > 0:
                    portion = wager / w_yes if w_yes > 0 else 0
                    shares_won = total_yes_created * portion
                    if trader_id == "whale":
                        self.state.whale_shares[asset_id] = self.state.whale_shares.get(asset_id, 0.0) + shares_won
                    else:
                        trader_obj.shares[asset_id] = trader_obj.shares.get(asset_id, 0.0) + shares_won
                else:
                    portion = abs(wager) / w_no if w_no > 0 else 0
                    shares_won = total_no_created * portion
                    if trader_id == "whale":
                        self.state.whale_shares[asset_id] = self.state.whale_shares.get(asset_id, 0.0) - shares_won
                    else:
                        trader_obj.shares[asset_id] = trader_obj.shares.get(asset_id, 0.0) - shares_won
            
            p_after = self.state.get_asset_price(asset_id)
            logging.info(f"Batch Executed [{asset_id}]: W_yes={w_yes:.2f}, W_no={w_no:.2f}, Q_match={q_match:.2f}, P_after={p_after:.4f}")

    def _create_verifier_from_path(self, agent_id: str, source_path: str) -> Optional[str]:
        """Creates a verifier package by copying from agent's worktree."""
        import hashlib
        import os
        
        if not os.path.exists(os.path.join(source_path, "run.sh")):
            logging.warning(f"Verifier at {source_path} missing run.sh")
            return None
            
        # Deterministic ID based on content of all relevant files in the directory
        # This prevents collisions when different tests use the same run.sh content.
        hasher = hashlib.md5()
        # Sort files to ensure deterministic hashing
        for root, _, files in os.walk(source_path):
            for fname in sorted(files):
                # Include standard test file types
                if fname.endswith(('.py', '.sh', '.json', '.txt', '.csv')):
                    fpath = os.path.join(root, fname)
                    with open(fpath, "rb") as f:
                        # Update hash with relative path and content
                        rel_path = os.path.relpath(fpath, source_path)
                        hasher.update(rel_path.encode())
                        hasher.update(f.read())
        
        content_hash = hasher.hexdigest()[:8]
        vid = f"v_{content_hash}"
        
        if vid in self.state.assets: return vid 
        
        v_dir = os.path.join(self.verifiers_dir, vid)
        if os.path.exists(v_dir):
            shutil.rmtree(v_dir)
            
        shutil.copytree(source_path, v_dir)
        os.chmod(v_dir, 0o755)
        
        # Ensure executable
        os.chmod(os.path.join(v_dir, "run.sh"), 0o755)
            
        # Write metadata.json
        with open(os.path.join(v_dir, "metadata.json"), "w") as f:
            json.dump({"proposer": agent_id, "timestamp": time.time()}, f)
            
        # Register in Market
        self.state.assets[vid] = MarketAsset(
            id=vid,
            type="VERIFIER",
            description=f"Verifier by {agent_id}",
            test_path=v_dir
        )
        
        return vid

    def _create_verifier(self, agent_id: str, proposal: Dict) -> Optional[str]:
        """Creates a verifier package in the filesystem."""
        import hashlib
        
        files = proposal.get("files", {})
        code = proposal.get("code", "")
        
        # Backward compatibility / simplified mode
        if code and not files:
            files = {
                "test.py": code,
                "run.sh": "#!/bin/bash\npython3 test.py\n"
            }
            
        if not files or "run.sh" not in files:
            logging.warning(f"Verifier proposal from {agent_id} missing run.sh")
            return None
            
        # Deterministic ID based on content of run.sh + (test.py if exists)
        # This is a simplification; ideally hash all files.
        content_hash = hashlib.md5(json.dumps(files, sort_keys=True).encode()).hexdigest()[:8]
        vid = f"v_{content_hash}"
        
        if vid in self.state.assets: return vid # Already exists
        
        v_dir = os.path.join(self.verifiers_dir, vid)
        os.makedirs(v_dir, exist_ok=True)
        os.chmod(v_dir, 0o755)
        
        for fname, content in files.items():
            fpath = os.path.join(v_dir, fname)
            # Prevent directory traversal
            if ".." in fname or fname.startswith("/"): continue
            
            # Ensure subdirectories exist if fname has them
            f_dirname = os.path.dirname(fpath)
            if f_dirname and not os.path.exists(f_dirname):
                os.makedirs(f_dirname, exist_ok=True)
            
            if fname == "run.sh":
                if not content.startswith("#!"):
                    content = "#!/bin/bash\n" + content
            
            with open(fpath, "w") as f:
                f.write(content)
                
            if fname == "run.sh":
                os.chmod(fpath, 0o755)
            else:
                os.chmod(fpath, 0o644)
            
        # Write metadata.json
        with open(os.path.join(v_dir, "metadata.json"), "w") as f:
            json.dump({"proposer": agent_id, "timestamp": time.time()}, f)
            
        # Register in Market
        self.state.assets[vid] = MarketAsset(
            id=vid,
            type="VERIFIER",
            description=f"Verifier by {agent_id}",
            test_path=v_dir
        )
        
        return vid

    async def _run_oracle(self):
        """Executes all verifiers against all candidates in parallel."""
        import asyncio
        candidates = [a for a in self.state.assets.values() if a.type == "CANDIDATE"]
        verifiers = [a for a in self.state.assets.values() if a.type == "VERIFIER"]
        
        tasks = []
        task_info = []

        for v in verifiers:
            for c in candidates:
                if not v.test_path or not c.code_path: continue
                
                # Pass the worktree root directly to the Oracle
                # The Oracle will handle copying the full tree and running the verifier
                tasks.append(Oracle.run_test(c.code_path, v.test_path))
                task_info.append((v, c))

        if not tasks:
            return

        results = await asyncio.gather(*tasks)

        for (v, c), result in zip(task_info, results):
            fail_key = f"{v.id}:{c.id}"
            if result == "FAIL":
                logging.info(f"Oracle: {c.id} FAILED {v.id}")
                self.state.test_failures[fail_key] = True
            elif result == "PASS":
                msg = f"Oracle: {c.id} PASSED {v.id}"
                if fail_key in self.state.test_failures:
                    msg += " (FIXED)"
                    self.state.test_failures.pop(fail_key, None)
                logging.info(msg)
            elif result == "TIMEOUT":
                logging.info(f"Oracle: {c.id} TIMEOUT on {v.id}")
            elif result == "ERROR":
                logging.info(f"Oracle: {c.id} ERROR on {v.id} (Check if solution.py exists)")

    def _mature_bonds(self):
        """Liquidates bonds that have reached their unlock round."""
        matured = [b for b in self.state.bonds if b.unlock_round <= self.state.round_num]
        if matured:
            logging.info(f"Maturing {len(matured)} bonds")
            
        for bond in matured:
            self._liquidate_shares(bond.agent_id, bond.asset_id, bond.q_shares)
            self.state.bonds.remove(bond)

    def get_pretty_summary(self) -> str:
        lines = []
        lines.append(f"--- Round {self.state.round_num} Summary ---")
        
        # Assets
        lines.append("Market Prices:")
        sorted_ids = sorted(self.state.assets.keys(), key=lambda x: (self.state.assets[x].type, x))
        for aid in sorted_ids:
            p = self.state.get_asset_price(aid)
            lines.append(f"  {aid}: {p:.3f}")
        
        # Agents
        lines.append("Agent Wealth:")
        sorted_agents = sorted(self.state.agents.values(), key=lambda a: a.wealth, reverse=True)
        for agent in sorted_agents:
            lines.append(f"  {agent.agent_id}: {agent.wealth:.2f}")

        lines.append(f"Whale Wealth: {self.state.whale_wealth:.2f}")
        lines.append("-" * 30)
        return "\n".join(lines)

    def get_final_report(self) -> str:
        """Generates a markdown report of the tournament results."""
        # 1. Determine Winner (Design 2.D.WinnerSelection)
        candidates = [a for a in self.state.assets.values() if a.type == "CANDIDATE"]
        if not candidates:
            return "Tournament concluded with no candidates."
            
        # Get prices and sort
        cand_prices = []
        for c in candidates:
            cand_prices.append((c.id, self.state.get_asset_price(c.id)))
        
        cand_prices.sort(key=lambda x: x[1], reverse=True)
        
        winner_id, max_price = cand_prices[0]
        epsilon_tie = 0.01
        
        # Check for ties within epsilon
        tied_candidates = [cid for cid, p in cand_prices if abs(p - max_price) < epsilon_tie]
        
        if len(tied_candidates) > 1:
            logging.info(f"Tie detected between {tied_candidates}. Using failure count tiebreaker.")
            # Tiebreaker: Lowest failure count on valid tests (P > 0.5)
            best_cid = winner_id
            min_failures = float('inf')
            
            valid_verifiers = [vid for vid, a in self.state.assets.items() 
                              if a.type == "VERIFIER" and self.state.get_asset_price(vid) > 0.5]
            
            for cid in tied_candidates:
                failures = 0
                for vid in valid_verifiers:
                    if self.state.test_failures.get(f"{vid}:{cid}"):
                        failures += 1
                
                if failures < min_failures:
                    min_failures = failures
                    best_cid = cid
                elif failures == min_failures:
                    # If still tied, the one with the higher price wins
                    current_best_p = next(p for cid_p, p in cand_prices if cid_p == best_cid)
                    this_p = next(p for cid_p, p in cand_prices if cid_p == cid)
                    if this_p > current_best_p:
                        best_cid = cid
            
            winner_id = best_cid
            max_price = next(p for cid_p, p in cand_prices if cid_p == winner_id)

        lines = [f"## Tournament Complete"]
        lines.append(f"**Winner:** {winner_id} (Market Confidence: {max_price:.1%})\n")
        
        # 2. Winning Code / Diff
        winner = self.state.assets[winner_id]
        if winner.code_path and os.path.isdir(winner.code_path):
            try:
                # Stage changes to capture new files
                subprocess.run("git add .", shell=True, check=True, cwd=winner.code_path, capture_output=True)
                
                # Get raw diff
                result = subprocess.run(
                    ["git", "diff", "--cached", "HEAD"], 
                    cwd=winner.code_path, 
                    capture_output=True, 
                    text=True
                )
                
                if not result.stdout.strip():
                     lines.append("_No changes made to the codebase._\n")
                     # Fallback to solution.py content
                     main_file = os.path.join(winner.code_path, "solution.py")
                     if os.path.exists(main_file):
                        with open(main_file, "r") as f:
                            lines.append(f"### Full Content of solution.py\n```python\n{f.read()}\n```\n")
                else:
                    # Process Diff with Truncation
                    full_diff = result.stdout
                    processed_diff = []
                    current_file_lines = []
                    in_hunk = False
                    file_header = ""
                    
                    # Split by file diffs (diff --git a/...)
                    raw_lines = full_diff.split('\n')
                    
                    current_file_diff = []
                    for line in raw_lines:
                        if line.startswith("diff --git"):
                            # Process previous file
                            if current_file_diff:
                                if len(current_file_diff) > 100:
                                    processed_diff.extend(current_file_diff[:100])
                                    processed_diff.append(f"... (Truncated {len(current_file_diff) - 100} lines. Use 'git diff' to see full changes) ...")
                                else:
                                    processed_diff.extend(current_file_diff)
                            current_file_diff = [line]
                        else:
                            current_file_diff.append(line)
                            
                    # Process last file
                    if current_file_diff:
                        if len(current_file_diff) > 100:
                            processed_diff.extend(current_file_diff[:100])
                            processed_diff.append(f"... (Truncated {len(current_file_diff) - 100} lines) ...")
                        else:
                            processed_diff.extend(current_file_diff)

                    lines.append(f"### Proposed Changes (Diff)\n```diff\n" + "\n".join(processed_diff) + "\n```\n")
                    lines.append("> **Note:** Large diffs are truncated. To view the full diff, run:\n> `cd " + winner.code_path + " && git diff --cached HEAD`\n")

            except Exception as e:
                lines.append(f"_Failed to generate diff: {e}_")
                lines.append("\n")
                # Fallback to full content
                main_file = os.path.join(winner.code_path, "solution.py")
                if os.path.exists(main_file):
                    with open(main_file, "r") as f:
                         lines.append(f"### Full Content of solution.py\n```python\n{f.read()}\n```\n")
        
        # 3. Validated Test Suite
        lines.append("### Validated Test Suite")
        lines.append("The market validated the following tests as correct:\n")
        
        valid_tests = []
        for aid, asset in self.state.assets.items():
            if asset.type == "VERIFIER":
                p = self.state.get_asset_price(aid)
                if p > 0.5: # 50% threshold for validity
                    if asset.test_path:
                        test_file = os.path.join(asset.test_path, "test.py")
                        if os.path.exists(test_file):
                            with open(test_file, "r") as f:
                                test_code = f.read()
                            valid_tests.append(f"#### {aid} (Confidence: {p:.1%})\n```python\n{test_code}\n```")
        
        if valid_tests:
            lines.extend(valid_tests)
        else:
            lines.append("_No tests achieved majority market validation._")
            
        lines.append("\n---\n")
        lines.append("> **Action Required:** Please apply the changes to your project.")
        lines.append("> ")
        lines.append("> **Apply Diff (Recommended)**")
        lines.append("> Use the `patch` command or your editor to apply the diff above.")
        lines.append("> ")
        lines.append("> **Save Validated Tests:**")
        lines.append("> If new tests were validated, save them to your `tests/` directory (e.g., `tests/test_tournament.py`) to prevent regression.")
        
        return "\n".join(lines)

    def get_summary(self):
        return {
            "round": self.state.round_num,
            "prices": {k: self.state.get_asset_price(k) for k in self.state.assets},
            "wealth": {k: v.wealth for k, v in self.state.agents.items()},
            "whale": self.state.whale_wealth
        }