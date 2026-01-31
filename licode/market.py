import math
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

@dataclass
class AgentState:
    wealth: float
    is_bankrupt: bool = False
    name: str = "unknown"

@dataclass
class SentenceData:
    id: str
    text: str
    verifier_path: Optional[str]
    current_price: float = 0.5
    history: List[float] = field(default_factory=list)
    # Mapping of agent_id -> belief (probability)
    beliefs: Dict[str, float] = field(default_factory=dict)
    resolved_value: Optional[bool] = None  # None if open, True/False if settled

class MarketState:
    def __init__(self, agent_ids: List[str], initial_budget: float):
        self.sentences: Dict[str, SentenceData] = {}
        self.agents: Dict[str, AgentState] = {}
        
        # Initialize Inductive Agents (Minnows)
        num_agents = len(agent_ids)
        if num_agents > 0:
            agent_share = initial_budget / num_agents
            for aid in agent_ids:
                self.agents[aid] = AgentState(wealth=agent_share, name=aid)
        
        # Initialize Deductive Whale
        # Whale gets wealth equal to sum of all agents (50% of total system wealth)
        total_agent_wealth = sum(a.wealth for a in self.agents.values())
        self.agents["whale"] = AgentState(wealth=total_agent_wealth, name="Whale")
        
        # Configuration
        self.risk_aversion_eta = 0.1
        self.payout_alpha = 1.0

    def register_sentence(self, text: str, verifier_path: Optional[str] = None) -> str:
        """Registers a new sentence to the market."""
        # Simple ID generation
        s_id = f"s_{len(self.sentences)}"
        self.sentences[s_id] = SentenceData(
            id=s_id,
            text=text,
            verifier_path=verifier_path
        )
        return s_id

    def submit_belief(self, agent_id: str, sentence_id: str, probability: float):
        """
        Agents submit their belief (probability) for a sentence.
        This is the 'Action C (Bet)' from the design.
        """
        if agent_id not in self.agents:
            raise ValueError(f"Unknown agent {agent_id}")
        if self.agents[agent_id].is_bankrupt:
            return # Bankrupt agents can't trade

        if sentence_id not in self.sentences:
            raise ValueError(f"Unknown sentence {sentence_id}")
        
        # Clamp probability to avoid math errors (log(0))
        probability = max(1e-6, min(1.0 - 1e-6, probability))
        
        self.sentences[sentence_id].beliefs[agent_id] = probability

    def calculate_kappas(self) -> Dict[str, float]:
        """
        Calculates the risk-scaling constant (kappa) for each agent 
        based on their total exposure across ALL sentences (Multi-Asset Allocation).
        kappa = eta / max(1, L), where L = sum(|f*|)
        """
        kappas = {}
        for aid, agent in self.agents.items():
            if agent.is_bankrupt:
                kappas[aid] = 0.0
                continue
            
            L = 0.0
            for s_id, sentence in self.sentences.items():
                if sentence.resolved_value is not None:
                    continue # Ignore settled sentences for current exposure

                belief = sentence.beliefs.get(aid)
                if belief is None: continue
                
                p = sentence.current_price
                # Avoid div by zero
                p = max(1e-6, min(1.0-1e-6, p))
                
                try:
                    f = (belief - p) / (p * (1 - p))
                    L += abs(f)
                except ZeroDivisionError:
                    pass
            
            kappa = self.risk_aversion_eta / max(1.0, L)
            kappas[aid] = kappa
        return kappas

    def update_price(self, sentence_id: str, kappas: Optional[Dict[str, float]] = None):
        """
        Calculates the new Market Clearing Price based on Wealth-Weighted Centroid.
        Design: P = Sum(W * kappa * b) / Sum(W * kappa)
        """
        sentence = self.sentences[sentence_id]
        if sentence.resolved_value is not None:
            return # Already settled

        numerator = 0.0
        denominator = 0.0
        
        current_p = sentence.current_price
        
        # Use provided kappas or calculate locally (single-asset fallback)
        if kappas is None:
            # Fallback to single-asset calculation (L = |f*|)
            pass

        for agent_id, agent in self.agents.items():
            if agent.is_bankrupt:
                continue
            
            belief = sentence.beliefs.get(agent_id)
            if belief is None:
                continue # Agent is sitting out

            if kappas and agent_id in kappas:
                kappa = kappas[agent_id]
            else:
                # Fallback: Single-asset kappa calculation
                try:
                    p_safe = max(1e-6, min(1.0-1e-6, current_p))
                    kelly_f = (belief - p_safe) / (p_safe * (1 - p_safe))
                    L = abs(kelly_f)
                    kappa = self.risk_aversion_eta / max(1.0, L)
                except ZeroDivisionError:
                    kappa = 0.0
            
            w_k = agent.wealth * kappa
            
            numerator += w_k * belief
            denominator += w_k
            
        if denominator > 0:
            new_price = numerator / denominator
            sentence.current_price = new_price
            sentence.history.append(new_price)

    def settle_truth(self, sentence_id: str, result: bool, kappas: Optional[Dict[str, float]] = None):
        """
        Resolves a sentence and redistributes wealth.
        result: True (Pass), False (Fail).
        If result is None (Undefined), no wealth changes.
        """
        sentence = self.sentences[sentence_id]
        if sentence.resolved_value is not None:
            return # Already settled

        sentence.resolved_value = result
        
        # Payout: Scaled Linearized Redistribution
        # Delta W = alpha * W * kappa * [ ... ]
        
        # We need the price AT THE TIME OF SETTLEMENT (or the last traded price).
        price = sentence.current_price
        
        # If price is 0 or 1 (certainty), handled carefully
        price = max(1e-6, min(1.0 - 1e-6, price))
        
        for agent_id, agent in self.agents.items():
            if agent.is_bankrupt:
                continue
                
            belief = sentence.beliefs.get(agent_id)
            if belief is None:
                continue

            if kappas and agent_id in kappas:
                kappa = kappas[agent_id]
            else:
                # Re-calculate kappa locally (Single Asset Fallback)
                kelly_f = (belief - price) / (price * (1 - price))
                L = abs(kelly_f)
                kappa = self.risk_aversion_eta / max(1.0, L)
            
            # Log Scoring Rule adaptation from design
            if result:
                # Term 1: (b - P) / P
                score = (belief - price) / price
            else:
                # Term 2: (P - b) / (1 - P)
                score = (price - belief) / (1.0 - price)
                
            delta = self.payout_alpha * agent.wealth * kappa * score
            
            agent.wealth += delta
            
            # Check bankruptcy
            if agent.wealth < 1.0: # Threshold
                agent.is_bankrupt = True

    def deduct_round_costs(self, costs: Dict[str, float]):
        """
        Deducts inference costs (tokens/compute) from agents.
        Args:
            costs: Dictionary mapping agent_id to cost amount.
        """
        for aid, cost in costs.items():
            if aid in self.agents:
                agent = self.agents[aid]
                if not agent.is_bankrupt:
                    agent.wealth -= cost
                    if agent.wealth < 1.0:
                        agent.is_bankrupt = True

    def rebalance_whale(self):
        """
        Resets Whale's budget to sum of all other agents.
        """
        minnow_wealth = sum(a.wealth for a in self.agents.values() if a.name != "Whale")
        if "whale" in self.agents:
            self.agents["whale"].wealth = minnow_wealth
            self.agents["whale"].is_bankrupt = False # Whale is too big to fail (it gets bailed out/reset)

    def witness_trigger(self, candidate_i_id: str, candidate_j_id: str, 
                        test_passed_by_j: bool, test_passed_by_i: bool,
                        sentence_i_id: str):
        """
        The Whale Logic:
        If Candidate I fails a test (test_passed_by_i is False)
        AND Candidate J passes the same test (test_passed_by_j is True)
        THEN Whale bets 0.0 on sentence_i_id ("Candidate I is Good")
        """
        if test_passed_by_j and not test_passed_by_i:
            logger.info(f"WHALE WITNESS: {candidate_j_id} passed but {candidate_i_id} failed. Crushing {sentence_i_id}.")
            self.submit_belief("whale", sentence_i_id, 0.0)
