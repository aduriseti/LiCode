import os
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from market.core.state import MarketState, AgentPortfolio, MarketAsset
from market.core.lmsr import LMSRMarket
from market.core.strategy import Strategy
from market.logic.whale import Whale
from market.logic.oracle import Oracle

@dataclass
class AgentAction:
    agent_id: str
    beliefs: Dict[str, float] = field(default_factory=dict)
    proposals: List[Dict] = field(default_factory=list) # e.g. {"type": "VERIFIER", "code": "..."}

class Orchestrator:
    def __init__(self, prompt: str, n_agents: int, budget: float = 1000.0, state: Optional[MarketState] = None):
        if state:
            self.state = state
            self.inference_tax = 1.0
        else:
            self.state = MarketState(
                round_num=0,
                liquidity_b=budget / 20.0, # Initial liquidity
                whale_wealth=budget
            )
            self.inference_tax = 1.0 # Cost per round
            
            # Initialize Agents
            for i in range(n_agents):
                aid = f"agent_{i}"
                self.state.agents[aid] = AgentPortfolio(
                    agent_id=aid, 
                    wealth=budget / n_agents
                )
                # Initialize Candidate for each agent
                cid = f"cand_{i}"
                self.state.assets[cid] = MarketAsset(
                    id=cid, 
                    type="CANDIDATE", 
                    description=f"Solution by {aid}"
                )

    def process_round(self, actions: List[AgentAction]):
        """
        Executes one full market round.
        """
        self.state.round_num += 1
        logging.info(f"--- Round {self.state.round_num} ---")
        
        # 1. Oracle Execution (Simulated for now, or real if paths set)
        # We need actual paths to run Oracle. 
        # For this implementation, we will skip actual Oracle run 
        # unless paths are populated in assets.
        # We assume external process might update state.test_failures 
        # OR we run it here if we have code.
        
        # 2. Whale Logic (Active)
        # Calculate new beliefs based on failures
        whale_trades = Whale.generate_trades(self.state)
        self._execute_trades("whale", whale_trades)
        
        # 3. Agent Actions
        for action in actions:
            agent_id = action.agent_id
            if agent_id not in self.state.agents:
                continue
                
            agent = self.state.agents[agent_id]
            
            # A. Process Proposals (TODO: Bond logic)
            # For now, just ignore proposals or auto-approve
            
            # B. Process Beliefs -> Trades
            if action.beliefs:
                trades = Strategy.beliefs_to_trades(
                    action.beliefs, 
                    agent.wealth, 
                    self.state
                )
                self._execute_trades(agent_id, trades)
                
        # 4. Apply Taxes & Check Bankruptcy
        to_remove = []
        for aid, agent in self.state.agents.items():
            agent.wealth -= self.inference_tax
            if agent.wealth <= 0:
                logging.info(f"Agent {aid} went bankrupt!")
                to_remove.append(aid)
                
        for aid in to_remove:
            # Liquidate (simple removal for now)
            del self.state.agents[aid]
            
        # 5. Update Liquidity
        # Recalculate b based on new Whale Wealth
        active_mkts = len(self.state.assets)
        self.state.liquidity_b = LMSRMarket.calculate_liquidity(
            self.state.whale_wealth, 
            active_mkts, 
            min_b=10.0
        )

    def _execute_trades(self, trader_id: str, trades: List[tuple]):
        for asset_id, delta_q in trades:
            if asset_id not in self.state.assets:
                continue
                
            asset = self.state.assets[asset_id]
            
            # 1. Calculate Cost
            # Buying YES shares (positive delta) or NO shares (negative delta)
            # We treat positive delta as buying YES, negative as buying NO (technically selling YES)
            is_yes = delta_q > 0
            abs_delta = abs(delta_q)
            
            cost = LMSRMarket.calculate_trade_cost(
                asset.q_yes, 
                asset.q_no, 
                self.state.liquidity_b, 
                abs_delta if is_yes else 0, # Add to YES
                True 
            )
            
            # Wait, calculate_trade_cost args are (q_yes, q_no, b, delta, is_yes_share)
            # If I want to SELL YES (short), I pass negative delta?
            # My lmsr.py implementation:
            # if is_yes_share: new_cost = cost(q_yes + delta)
            # So yes, delta can be negative.
            
            cost = LMSRMarket.calculate_trade_cost(
                asset.q_yes,
                asset.q_no,
                self.state.liquidity_b,
                delta_q,
                True # We always trade YES shares (buy or sell)
            )
            
            # 2. Check Affordability
            if trader_id != "whale":
                agent = self.state.agents[trader_id]
                if cost > agent.wealth:
                    # Scale down trade
                    ratio = agent.wealth / cost if cost > 0 else 1.0
                    # If cost is negative (profit), we can always do it? 
                    # Usually yes. But if cost positive, check budget.
                    if ratio < 1.0:
                        delta_q *= ratio
                        cost *= ratio
            
            # 3. Execute
            asset.q_yes += delta_q
            
            # Update Wealth
            if trader_id == "whale":
                self.state.whale_wealth -= cost
            else:
                self.state.agents[trader_id].wealth -= cost
                
                # Update Portfolio Tracking
                current_shares = self.state.agents[trader_id].shares.get(asset_id, 0.0)
                self.state.agents[trader_id].shares[asset_id] = current_shares + delta_q

    def get_pretty_summary(self) -> str:
        lines = []
        lines.append(f"╔══════════════════════════════════════════════════════╗")
        lines.append(f"║ ROUND {self.state.round_num:<47}║")
        lines.append(f"╠══════════════════════╤═══════════╤══════════════════╣")
        lines.append(f"║ Candidate            │ Price     │ Status           ║")
        lines.append(f"╟──────────────────────┼───────────┼──────────────────╢")
        
        for aid, asset in self.state.assets.items():
            if asset.type == "CANDIDATE":
                p = self.state.get_asset_price(aid)
                # Simple ASCII bar
                bar_len = int(p * 15)
                bar = "█" * bar_len + "░" * (15 - bar_len)
                lines.append(f"║ {aid:<20} │ {p:>.3f}     │ {bar} ║")
        
        lines.append(f"╠══════════════════════╧═══════════╧══════════════════╣")
        lines.append(f"║ Whale Wealth: {self.state.whale_wealth:>38.2f} ║")
        lines.append(f"╚══════════════════════════════════════════════════════╝")
        return "\n".join(lines)

    def get_summary(self):
        return {
            "round": self.state.round_num,
            "prices": {k: self.state.get_asset_price(k) for k in self.state.assets},
            "wealth": {k: v.wealth for k, v in self.state.agents.items()},
            "whale": self.state.whale_wealth
        }
