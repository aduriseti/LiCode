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
    proposals: List[Dict] = field(default_factory=list) # e.g. {"type": "VERIFIER", "code": "..."}
    patch: Optional[str] = None # Code patch for their own candidate

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
                self.state.assets[c_id] = MarketAsset(
                    id=c_id, 
                    type="CANDIDATE", 
                    description=f"Solution by {a_id}",
                    code_path=c_dir # Point to ROOT of worktree
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
        
        # 1. Process Proposals (New Assets)
        for action in actions:
            for proposal in action.proposals:
                p_type = proposal.get("type")
                if p_type == "VERIFIER":
                    vid = self._create_verifier(action.agent_id, proposal)
                    if vid:
                        logging.info(f"Agent {action.agent_id} proposed new verifier: {vid}")
                
                elif p_type == "CANDIDATE" or p_type == "PATCH":
                    # Handle code updates
                    if action.agent_id in self.state.agents:
                        cid = f"cand_{action.agent_id.split('_')[-1]}"
                        if cid in self.state.assets:
                            asset = self.state.assets[cid]
                            if asset.code_path:
                                logging.info(f"Agent {action.agent_id} updating code for {cid} ({p_type})")
                                self._update_candidate_code(asset.code_path, proposal)

        # 2. Oracle Execution
        # Run all verifiers against all candidates
        await self._run_oracle()
        
        # 3. Mature Bonds (Unlock capital from previous rounds)
        self._mature_bonds()
        
        # 4. Whale Logic (Active)
        whale_trades = Whale.generate_trades(self.state)
        self._execute_trades("whale", whale_trades)
        
        # 4. Agent Actions (Bets)
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
                
        # 5. Apply Taxes & Check Bankruptcy
        to_remove = []
        for aid, agent in self.state.agents.items():
            agent.wealth -= self.inference_tax
            if agent.wealth <= 0:
                logging.info(f"Agent {aid} went bankrupt!")
                to_remove.append(aid)
                
        for aid in to_remove:
            del self.state.agents[aid]
            
        # 6. Update Liquidity
        active_mkts = len(self.state.assets)
        self.state.liquidity_b = LMSRMarket.calculate_liquidity(
            self.state.whale_wealth, 
            active_mkts, 
            min_b=10.0
        )

    def _update_candidate_code(self, worktree_root: str, proposal: Dict):
        """Applies updates to candidate code via full rewrite or patch."""
        # Proposal must specify file_path relative to root
        rel_path = proposal.get("file_path", "solution.py") # Default for back-compat
        
        # Prevent escaping worktree
        if ".." in rel_path or rel_path.startswith("/"):
            logging.error(f"Invalid file path: {rel_path}")
            return
            
        full_path = os.path.join(worktree_root, rel_path)
        
        # If worktree_root is a file (common in tests), rel_path should be empty or we just use worktree_root
        if os.path.isfile(worktree_root):
            full_path = worktree_root

        try:
            # Ensure dir exists if new file
            dir_name = os.path.dirname(full_path)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name, exist_ok=True)
            
            if os.path.exists(full_path) and os.path.isfile(full_path):
                with open(full_path, "r") as f:
                    content = f.read()
            else:
                content = ""
                
            p_type = proposal.get("type")
            if p_type == "CANDIDATE":
                # Full rewrite
                new_content = proposal.get("code", "")
                with open(full_path, "w") as f:
                    f.write(new_content)
                logging.info(f"Updated {rel_path} via CANDIDATE (overwrite)")
                    
            elif p_type == "PATCH":
                # Search and Replace
                old_code = proposal.get("old_code", "")
                new_code = proposal.get("new_code", "")
                
                if not old_code:
                    # If file is empty, maybe append?
                    # Strict patch: if old_code not found, fail.
                    logging.warning("PATCH failed: 'old_code' is empty.")
                    return

                if content.count(old_code) == 0:
                    logging.warning(f"PATCH failed: 'old_code' not found in {rel_path}.")
                    return
                elif content.count(old_code) > 1:
                    logging.warning(f"PATCH failed: 'old_code' found multiple times in {rel_path}.")
                    return
                    
                new_content = content.replace(old_code, new_code)
                with open(full_path, "w") as f:
                    f.write(new_content)
                logging.info(f"Updated {rel_path} via PATCH")
                    
        except Exception as e:
            logging.error(f"Failed to update code {full_path}: {e}")

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
                
                # Strategy: If candidate is a directory, we pass 'solution.py' inside it.
                cand_file = c.code_path
                if os.path.isdir(cand_file):
                    cand_file = os.path.join(cand_file, "solution.py")
                
                tasks.append(Oracle.run_test(cand_file, v.test_path))
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
            
            # Update Wealth
            new_wealth = 0.0
            if trader_id == "whale":
                self.state.whale_wealth -= cost
                new_wealth = self.state.whale_wealth
                
                # Update Whale Portfolio
                current_shares = self.state.whale_shares.get(asset_id, 0.0)
                self.state.whale_shares[asset_id] = current_shares + delta_q
            else:
                self.state.agents[trader_id].wealth -= cost
                new_wealth = self.state.agents[trader_id].wealth
                
                # Update Portfolio Tracking
                current_shares = self.state.agents[trader_id].shares.get(asset_id, 0.0)
                self.state.agents[trader_id].shares[asset_id] = current_shares + delta_q
            
            logging.info(f"Trade Executed [{trader_id}]: Asset={asset_id}, Delta={delta_q:.2f} (d_yes={d_yes:.2f}, d_no={d_no:.2f}), Cost={cost:.2f}, NewWealth={new_wealth:.2f}, NewState(q_yes={asset.q_yes:.2f}, q_no={asset.q_no:.2f})")

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
        # 1. Determine Winner
        winner_id = ""
        max_price = -1.0
        
        for aid, asset in self.state.assets.items():
            if asset.type == "CANDIDATE":
                p = self.state.get_asset_price(aid)
                if p > max_price:
                    max_price = p
                    winner_id = aid
        
        if not winner_id:
            return "Tournament concluded with no candidates."

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