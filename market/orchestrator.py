import os
import json
import logging
import time
import hashlib
import shutil
import subprocess
import asyncio
from typing import Dict, List, Optional
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
        """Clones the project workspace to the destination, respecting .gitignore."""
        src = os.getcwd()
        os.makedirs(dest_dir, exist_ok=True)
        
        # Performance optimized clone:
        # 1. 'git ls-files' finds all tracked and untracked (non-ignored) files.
        # 2. 'tar' stream copies them to the destination.
        cmd = f"git ls-files -co --exclude-standard -z | tar -c --null -T - | tar -x -C {dest_dir}"
        
        try:
            subprocess.run(cmd, shell=True, check=True, cwd=src, capture_output=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Cloning failed: {e.stderr.decode()}")
            raise

        # Ensure write permissions (tar preserves permissions, but we want 755 on dirs and 644 on files)
        for root, dirs, files in os.walk(dest_dir):
            os.chmod(root, 0o755)
            for f in files:
                os.chmod(os.path.join(root, f), 0o644)

    async def process_round(self, actions: List[AgentAction]):
        """
        Executes one full market round.
        """
        import asyncio
        self.state.round_num += 1
        logging.info(f"--- Round {self.state.round_num} ---")
        
        # 0. Liquidity is now FIXED at budget/20.0 (set in __init__)
        # No scaling or dynamic recalculation.

        # 1. Process Proposals (New Assets)
        for action in actions:
            for proposal in action.proposals:
                p_type = proposal.get("type")
                if p_type == "VERIFIER":
                    # Agent must have written files to their worktree first
                    cid = f"cand_{action.agent_id.split('_')[-1]}"
                    if cid in self.state.assets:
                        candidate = self.state.assets[cid]
                        source_path = proposal.get("path")
                        if source_path and candidate.code_path:
                            full_source = os.path.join(candidate.code_path, source_path)
                            if os.path.isdir(full_source):
                                vid = self._create_verifier_from_path(action.agent_id, full_source)
                                if vid:
                                    logging.info(f"Agent {action.agent_id} proposed new verifier: {vid}")
                            else:
                                logging.warning(f"Agent {action.agent_id} proposed verifier at non-existent path: {source_path}")

        # 2. Mature Bonds (Unlock capital from previous rounds)
        self._mature_bonds()
        
        # 3. Agent Actions (Bets) - Execute before Oracle/Whale to allow alpha capture (Design 4.H Step 7)
        for action in actions:
            agent_id = action.agent_id
            if agent_id not in self.state.agents:
                continue
                
            agent = self.state.agents[agent_id]
            if action.beliefs:
                trades = Strategy.beliefs_to_trades(
                    action.beliefs, 
                    agent.wealth, 
                    self.state
                )
                self._execute_trades(agent_id, trades)

        # 4. Oracle Execution (Design 4.H Step 2)
        await self._run_oracle()

        # 5. Whale Logic (Active Deductive) - Execute after agents (Design 4.H Step 7)
        whale_trades = Whale.generate_trades(self.state)
        self._execute_trades("whale", whale_trades)
        
        # 6. INSTANT SETTLEMENT
        # Mark-to-Market all belief-based trades at the end of the round.
        # Locked bonds are EXCLUDED.
        self._settle_all_bets()

        # 7. Apply Taxes & Check Bankruptcy
        to_remove = []
        for aid, agent in self.state.agents.items():
            agent.wealth -= self.inference_tax
            if agent.wealth <= 0:
                logging.info(f"Agent {aid} went bankrupt!")
                to_remove.append(aid)
                
        for aid in to_remove:
            agent = self.state.agents[aid]
            # Force liquidate any remaining bonds for this agent
            agent_bonds = [b for b in self.state.bonds if b.agent_id == aid]
            for bond in agent_bonds:
                # Proceed with liquidation trades. Cost will be negative (payout).
                self._execute_trades(aid, [(bond.asset_id, -bond.q_shares)])
                self.state.bonds.remove(bond)
            
            # Transfer remaining estate to the Whale (Escheatment)
            # This ensures zero-sum conservation when an agent is deleted.
            if agent.wealth != 0:
                logging.info(f"Agent {aid} estate of {agent.wealth:.2f} escheated to Whale.")
                self.state.whale_wealth += agent.wealth
                agent.wealth = 0.0
                
            del self.state.agents[aid]

    def _settle_all_bets(self):
        """
        Resolves all non-bond positions for the round by transferring their credit value
        from the Whale to the Agents. Price discovery is preserved.
        """
        # Map of agent_id -> asset_id -> shares_to_keep (from bonds)
        locked_shares = {}
        for bond in self.state.bonds:
            if bond.agent_id not in locked_shares:
                locked_shares[bond.agent_id] = {}
            locked_shares[bond.agent_id][bond.asset_id] = locked_shares[bond.agent_id].get(bond.asset_id, 0.0) + bond.q_shares

        # 1. Settle Agents: Calculate payout for non-bond shares
        for aid, agent in self.state.agents.items():
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
                    
                    # Clear the exposure from agent
                    if abs(locked) < 0.0001:
                        del agent.shares[asset_id]
                    else:
                        agent.shares[asset_id] = locked
                    
                    if abs(payout) > 0.0001:
                        logging.info(f"Settlement: Agent {aid} received {payout:.2f} payout for {asset_id} position ({exposure:.2f} shares)")

    def _create_verifier_from_path(self, agent_id: str, source_path: str) -> Optional[str]:
        """Creates a verifier package by copying from agent's worktree."""
        import hashlib
        
        if not os.path.exists(os.path.join(source_path, "run.sh")):
            logging.warning(f"Verifier at {source_path} missing run.sh")
            return None
            
        # Deterministic ID based on content of directory
        # We'll just hash the run.sh for speed, ideally should hash all
        with open(os.path.join(source_path, "run.sh"), "rb") as f:
            content_hash = hashlib.md5(f.read()).hexdigest()[:8]
            
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
        
        # Bond logic (Force buy YES shares)
        if agent_id in self.state.agents:
            agent = self.state.agents[agent_id]
            # Use Strategy to calculate bond size (buying YES shares)
            bond_trades = Strategy.beliefs_to_trades(
                {vid: 1.0 - self.epsilon}, 
                agent.wealth, 
                self.state
            )
            if bond_trades:
                self._execute_trades(agent_id, bond_trades)
                q_shares = agent.shares.get(vid, 0.0)
                if q_shares > 0:
                    self.state.bonds.append(MarketBond(
                        agent_id=agent_id,
                        asset_id=vid,
                        q_shares=q_shares,
                        unlock_round=self.state.round_num + self.bond_lock_period
                    ))
                    logging.info(f"Created bond for {agent_id} on {vid}: {q_shares:.2f} shares")

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
        
        # Bond logic (Force buy YES shares)
        if agent_id in self.state.agents:
            agent = self.state.agents[agent_id]
            # Use Strategy to calculate bond size (buying YES shares)
            bond_trades = Strategy.beliefs_to_trades(
                {vid: 1.0 - self.epsilon}, 
                agent.wealth, 
                self.state
            )
            if bond_trades:
                # Execute the trade
                self._execute_trades(agent_id, bond_trades)
                # Record the bond for later maturation
                q_shares = agent.shares.get(vid, 0.0)
                if q_shares > 0:
                    self.state.bonds.append(MarketBond(
                        agent_id=agent_id,
                        asset_id=vid,
                        q_shares=q_shares,
                        unlock_round=self.state.round_num + self.bond_lock_period
                    ))
                    logging.info(f"Created bond for {agent_id} on {vid}: {q_shares:.2f} shares")

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
            # Sell back shares: delta_q = -q_shares
            # We use _execute_trades which handles wealth updates and share tracking
            self._execute_trades(bond.agent_id, [(bond.asset_id, -bond.q_shares)])
            self.state.bonds.remove(bond)

    def _execute_trades(self, trader_id: str, trades: List[tuple]):
        if trades:
            logging.info(f"Executing {len(trades)} trades for {trader_id}")
        for asset_id, delta_q in trades:
            if asset_id not in self.state.assets:
                continue
                
            asset = self.state.assets[asset_id]
            b = self.state.liquidity_b
            
            # --- 1. Determine Trade Structure (d_yes, d_no) ---
            # We map the requested 'net delta' into changes in YES and NO shares
            # based on the agent's current holding.
            
            current_pos = 0.0
            if trader_id != "whale":
                current_pos = self.state.agents[trader_id].shares.get(asset_id, 0.0)
            else:
                current_pos = self.state.whale_shares.get(asset_id, 0.0)
            
            d_yes = 0.0
            d_no = 0.0
            
            if delta_q > 0:
                # Buying YES (Net Long)
                if current_pos < 0:
                    # Covering Short: Sell NO shares back
                    # current_pos is negative (e.g. -10). We want to buy +15.
                    # Cover 10 NO shares (d_no = -10), then Buy 5 YES (d_yes = +5).
                    cover_amt = min(delta_q, abs(current_pos))
                    d_no -= cover_amt
                    rem_delta = delta_q - cover_amt
                    d_yes += rem_delta
                else:
                    # Already Long or Neutral: Just Buy YES
                    d_yes += delta_q
                    
            elif delta_q < 0:
                # Selling YES / Buying NO (Net Short)
                abs_delta = abs(delta_q)
                if current_pos > 0:
                    # Closing Long: Sell YES shares back
                    # current_pos is 10. We want to sell -15.
                    # Sell 10 YES (d_yes = -10), then Buy 5 NO (d_no = +5).
                    sell_amt = min(abs_delta, current_pos)
                    d_yes -= sell_amt
                    rem_delta = abs_delta - sell_amt
                    d_no += rem_delta
                else:
                    # Already Short or Neutral: Just Buy NO
                    d_no += abs_delta

            # --- 2. Calculate Cost ---
            # Cost = C(new) - C(old)
            old_cost = LMSRMarket.cost_function(asset.q_yes, asset.q_no, b)
            new_cost = LMSRMarket.cost_function(asset.q_yes + d_yes, asset.q_no + d_no, b)
            cost = new_cost - old_cost
            
            # --- 3. Check Affordability ---
            if trader_id != "whale":
                agent = self.state.agents[trader_id]
                if cost > agent.wealth:
                    # Scale down trade
                    # If cost is positive (paying), we are limited by budget.
                    # If cost is negative (profit), we are not limited.
                    if cost > 0:
                        ratio = agent.wealth / cost
                        d_yes *= ratio
                        d_no *= ratio
                        # Recalculate cost
                        new_cost = LMSRMarket.cost_function(asset.q_yes + d_yes, asset.q_no + d_no, b)
                        cost = new_cost - old_cost

            # --- 4. Execute ---
            asset.q_yes += d_yes
            asset.q_no += d_no
            
            # Update Wealth (Symmetric Zero-Sum Logic)
            if trader_id != "whale":
                # Agents pay the Market Maker (The Whale)
                self.state.agents[trader_id].wealth -= cost
                self.state.whale_wealth += cost
                
                # Update Agent Portfolio
                current_shares = self.state.agents[trader_id].shares.get(asset_id, 0.0)
                self.state.agents[trader_id].shares[asset_id] = current_shares + delta_q
            
            # Whale trades only move the global pool (the MM inventory).
            # No internal wealth transfer is needed because Whale wealth IS the MM pool.
            
            p_after = self.state.get_asset_price(asset_id)
            logging.info(f"Trade Executed [{trader_id}]: Asset={asset_id}, Delta={delta_q:.2f} (d_yes={d_yes:.2f}, d_no={d_no:.2f}), Cost={cost:.2f}, P_after={p_after:.4f}")

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
            # Generate diff between original workspace and winning worktree
            # Original: os.getcwd() (Project Root)
            # Winner: winner.code_path
            
            # Use diff -ur to get recursive unified diff
            # Exclude .git, .arenas, etc. to avoid noise
            try:
                # We need to be careful about absolute paths in diff headers
                # We want paths relative to project root
                cmd = [
                    "diff", "-urN",
                    "--exclude=.git", "--exclude=.arenas", "--exclude=__pycache__", "--exclude=node_modules", "--exclude=.home",
                    ".", # Original (Current Dir)
                    winner.code_path # New
                ]
                
                # Run diff
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                # Diff returns exit code 1 if differences found, 0 if same
                if result.returncode > 1:
                    lines.append(f"_Error generating diff: {result.stderr}_")
                    lines.append("\n")
                elif not result.stdout.strip():
                    lines.append("_No changes made to the codebase._\n")
                    # Still try to show the main file content as a fallback context
                    main_file = os.path.join(winner.code_path, "solution.py")
                    if os.path.exists(main_file):
                        with open(main_file, "r") as f:
                            lines.append(f"### Full Content of solution.py\n```python\n{f.read()}\n```\n")
                else:
                    lines.append(f"### Proposed Changes (Diff)\n```diff\n{result.stdout}\n```\n")
                    
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