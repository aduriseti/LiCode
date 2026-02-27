import math
import logging
from typing import Dict, List, Tuple, Optional

# Use relative imports if running as package, or assume PYTHONPATH set
from ..core.lmsr import LMSRMarket
from ..core.state import MarketState
from ..core.strategy import Strategy

class Whale:
    """
    The Deductive Agent and Market Maker.
    
    Roles:
    1. Passive: Provides liquidity via LMSR (implicit in market mechanics).
    2. Active: Corrects candidate prices based on test failures using Kelly Strategy.
    """
    
    @staticmethod
    def compute_survival_scores(state: MarketState, verifier_prices: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        """
        Calculates log-survival score for each candidate.
        S_i = Sum( ln(1 - P(Verifier_j)) ) for all j where i failed j.
        
        Interpretation:
        - If candidate fails a valid test (P close to 1), S_i drops massively.
        - If candidate fails an invalid test (P close to 0), S_i drops slightly.
        """
        scores = {}
        
        # Identify all candidates
        candidates = [aid for aid, a in state.assets.items() if a.type == "CANDIDATE"]
        
        # Determine which probabilities to use
        # If verifier_prices is provided, use those (e.g. start-of-round prices)
        # Otherwise fall back to current state prices
        if verifier_prices is None:
            verifier_probs = {}
            for aid, asset in state.assets.items():
                if asset.type == "VERIFIER":
                    verifier_probs[aid] = state.get_asset_price(aid)
        else:
            verifier_probs = verifier_prices
                
        for cid in candidates:
            score = 0.0
            # Find all failures for this candidate
            # Failure key format "verifier_id:candidate_id"
            for fail_key in state.test_failures:
                vid, failed_cid = fail_key.split(":")
                if failed_cid == cid:
                    # Get probability that this verifier is VALID
                    # Default to 0.5 if it's a brand new verifier not in pre-trade prices
                    p_valid = verifier_probs.get(vid, 0.5)
                    
                    # Avoid log(0)
                    prob_safe = min(p_valid, 0.9999)
                    
                    # Log survival: ln(probability code is correct given this failure)
                    # If test is valid, code is incorrect -> probability 0 -> ln(0) -> -inf
                    # We model probability code survives test = (1 - p_valid)
                    score += math.log(1.0 - prob_safe)
            
            scores[cid] = score
            
        return scores

    @staticmethod
    def compute_whale_beliefs(scores: Dict[str, float]) -> Dict[str, float]:
        """
        Converts survival scores to probability distribution via Softmax.
        """
        # Softmax stability trick
        if not scores:
            return {}
            
        # If all scores are 0, it means no failures have occurred yet.
        # In this case, the Whale should NOT have an active opinion/belief,
        # allowing the market to be driven by inductive agents initially.
        if all(s == 0.0 for s in scores.values()):
            return {}
            
        max_s = max(scores.values())
        exps = {cid: math.exp(s - max_s) for cid, s in scores.items()}
        total_exp = sum(exps.values())
        
        return {cid: v / total_exp for cid, v in exps.items()}

    @staticmethod
    def generate_trades(state: MarketState, verifier_prices: Optional[Dict[str, float]] = None) -> List[Tuple[str, float]]:
        """
        Determines what trades the Whale should make to enforce logic.
        Uses the Kelly Strategy for active trading.
        
        Returns:
            List of (asset_id, delta_q)
        """
        scores = Whale.compute_survival_scores(state, verifier_prices=verifier_prices)
        active_beliefs = Whale.compute_whale_beliefs(scores)
        
        # LOGGING ONLY: Compute logical beliefs (softmax) for observability
        if scores:
            max_s = max(scores.values())
            exps = {cid: math.exp(s - max_s) for cid, s in scores.items()}
            total_exp = sum(exps.values())
            logical_beliefs = {cid: round(v / total_exp, 4) for cid, v in exps.items()}
            
            logging.info(f"Whale Analysis - Scores: {scores}")
            logging.info(f"Whale Analysis - Beliefs (Logical): {logical_beliefs}")
            if not active_beliefs:
                logging.info(f"Whale Decision: Neutral (No active trades)")
        
        if not active_beliefs:
            return []
            
        # The Whale trades using the same Kelly strategy as agents
        # (Design 2.C.2 and 4.C)
        return Strategy.beliefs_to_wagers(
            active_beliefs,
            state.whale_wealth,
            state
        )
