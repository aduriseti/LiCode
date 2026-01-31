import asyncio
import os
import tempfile
import shutil
import logging
from typing import List, Dict
import random
import json

from licode.market import MarketState, SentenceData
from licode.agent import Agent, Move, RandomAgent
from licode.verifier import Verifier

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self, prompt: str, agent_count: int = 3, budget: float = 1000.0):
        self.prompt = prompt
        self.agent_count = agent_count
        self.budget = budget
        
        self.temp_dir = tempfile.mkdtemp(prefix="licode_market_")
        self.worktrees_dir = os.path.join(self.temp_dir, "worktrees")
        self.verifiers_dir = os.path.join(self.temp_dir, "verifiers")
        
        os.makedirs(self.worktrees_dir, exist_ok=True)
        os.makedirs(self.verifiers_dir, exist_ok=True)
        
        self.agents: List[Agent] = []
        self.agent_ids: List[str] = []
        
        # Initialize Agents
        for i in range(agent_count):
            aid = f"minnow_{i}"
            self.agent_ids.append(aid)
            # For now, just using RandomAgent. In real usage, this would be LLM agents.
            self.agents.append(RandomAgent(aid))
            
            # Create worktree
            wt_path = os.path.join(self.worktrees_dir, aid)
            os.makedirs(wt_path, exist_ok=True)
            # Write initial dummy code
            with open(os.path.join(wt_path, "main.py"), "w") as f:
                f.write(f"# Agent {aid} initial code\ndef solve(): pass")

        self.market = MarketState(self.agent_ids, self.budget)
        
        # Register Initial Master Goals ("Candidate X is good")
        self.goal_sentences: Dict[str, str] = {} # agent_id -> sentence_id
        for aid in self.agent_ids:
            s_id = self.market.register_sentence(f"Candidate {aid} satisfies the user's prompt.")
            self.goal_sentences[aid] = s_id

    async def run_tournament(self, rounds: int = 5):
        logger.info(f"Starting tournament in {self.temp_dir}")
        
        for r in range(rounds):
            logger.info(f"--- Round {r+1}/{rounds} ---")
            await self.tick()
            
            # Basic reporting
            prices = {aid: self.market.sentences[sid].current_price 
                      for aid, sid in self.goal_sentences.items()}
            logger.info(f"Current Prices: {prices}")

        logger.info("Tournament Complete.")
        self.cleanup()

    async def tick(self):
        # 1. Snapshot
        snapshot = {
            "sentences": {sid: s.current_price for sid, s in self.market.sentences.items()},
            "wealth": {aid: self.market.agents[aid].wealth for aid in self.agent_ids}
        }
        
        # Write snapshot to disk
        with open(os.path.join(self.temp_dir, "market_state.json"), "w") as f:
            json.dump(snapshot, f, indent=2)
        
        # 2. Collect Moves (Parallel)
        tasks = [agent.get_next_move(snapshot) for agent in self.agents]
        moves: List[Move] = await asyncio.gather(*tasks)
        
        # Collect costs
        round_costs = {}
        
        # 3. Process Moves
        new_verifiers = []
        
        for idx, move in enumerate(moves):
            agent_id = self.agent_ids[idx]
            agent_wt = os.path.join(self.worktrees_dir, agent_id)
            
            # Track Cost
            round_costs[agent_id] = move.inference_cost
            
            # Action A: Propose Verifier
            if move.proposed_verifier_content:
                v_name = f"test_{random.randint(1000, 9999)}.py"
                v_path = os.path.join(self.verifiers_dir, v_name)
                with open(v_path, "w") as f:
                    f.write(move.proposed_verifier_content)
                
                # Register Sentence for this test
                s_id = self.market.register_sentence(f"Verifier {v_name} passes", verifier_path=v_path)
                new_verifiers.append((s_id, v_path))
                logger.info(f"Agent {agent_id} proposed verifier {v_name}")

            # Action B: Update Candidate
            if move.updated_code_content:
                with open(os.path.join(agent_wt, "main.py"), "w") as f:
                    f.write(move.updated_code_content)
                logger.info(f"Agent {agent_id} updated code.")

            # Action C: Bet
            for s_id, belief in move.belief_vector.items():
                try:
                    self.market.submit_belief(agent_id, s_id, belief)
                except ValueError:
                    pass # Ignore invalid sentences

        # 4. Oracle Run (Execute Verifiers)
        active_verifiers = [
            (sid, s.verifier_path) 
            for sid, s in self.market.sentences.items() 
            if s.verifier_path and s.resolved_value is None
        ]
        
        results_cache = {} # (verifier_id, agent_id) -> bool
        
        for s_id, v_path in active_verifiers:
            verifier = Verifier(v_path)
            # Run against all candidates
            for aid in self.agent_ids:
                wt_path = os.path.join(self.worktrees_dir, aid)
                result = verifier.execute(wt_path)
                results_cache[(s_id, aid)] = result

        # 5. Whale Witness Logic
        for s_id, v_path in active_verifiers:
            for i_id in self.agent_ids:
                res_i = results_cache.get((s_id, i_id))
                witness_found = False
                for j_id in self.agent_ids:
                    if i_id == j_id: continue
                    res_j = results_cache.get((s_id, j_id))
                    if res_j is True:
                        witness_found = True
                        break
                
                if res_i is False and witness_found:
                    goal_s_id = self.goal_sentences[i_id]
                    self.market.witness_trigger(i_id, "some_witness", True, False, goal_s_id)

        # 6. Update Prices (Multi-Asset)
        kappas = self.market.calculate_kappas()
        for s_id in self.market.sentences:
            self.market.update_price(s_id, kappas=kappas)

        # 7. Settlement
        for s_id, v_path in active_verifiers:
            for i_id in self.agent_ids:
                res_i = results_cache.get((s_id, i_id))
                witness_found = False
                for j_id in self.agent_ids:
                    if i_id == j_id: continue
                    if results_cache.get((s_id, j_id)) is True:
                        witness_found = True
                        break
                
                if res_i is False and witness_found:
                    goal_s_id = self.goal_sentences[i_id]
                    self.market.settle_truth(goal_s_id, False, kappas=kappas)

        # 8. Rebalance Whale & Deduct Costs
        self.market.rebalance_whale()
        
        # Deduct the collected inference costs
        self.market.deduct_round_costs(round_costs)

    def cleanup(self):
        shutil.rmtree(self.temp_dir)
