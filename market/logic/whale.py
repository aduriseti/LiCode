import math
import logging
from typing import Dict, List, Tuple

# Use relative imports if running as package, or assume PYTHONPATH set
from ..core.lmsr import LMSRMarket
from ..core.state import MarketState

class Whale:
    """
    The Deductive Agent and Market Maker.
    
    Roles:
    1. Passive: Provides liquidity via LMSR (implicit in market mechanics).
    2. Active: Corrects candidate prices based on test failures.
    """
    
    @staticmethod
    def compute_survival_scores(state: MarketState) -> Dict[str, float]:
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
        
        # Pre-calculate verifier probabilities to avoid repeated math
        verifier_probs = {}
        for aid, asset in state.assets.items():
            if asset.type == "VERIFIER":
                verifier_probs[aid] = state.get_asset_price(aid)
                
        for cid in candidates:
            score = 0.0
            # Find all failures for this candidate
            # Failure key format "verifier_id:candidate_id"
            for fail_key in state.test_failures:
                vid, failed_cid = fail_key.split(":")
                if failed_cid == cid:
                    # Get probability that this verifier is VALID
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
            
        max_s = max(scores.values())
        exps = {cid: math.exp(s - max_s) for cid, s in scores.items()}
        total_exp = sum(exps.values())
        
        return {cid: v / total_exp for cid, v in exps.items()}

    @staticmethod
    def generate_trades(state: MarketState) -> List[Tuple[str, float]]:
        """
        Determines what trades the Whale should make to enforce logic.
        
        Returns:
            List of (asset_id, delta_q)
        """
        scores = Whale.compute_survival_scores(state)
        beliefs = Whale.compute_whale_beliefs(scores)
        
        if scores:
            logging.info(f"Whale Analysis - Scores: {scores}")
            logging.info(f"Whale Analysis - Target Beliefs: {beliefs}")
        
        trades = []
        
        # For each candidate, Whale wants to move price to belief
        # This is a Kelly bet or direct price targeting.
        # For simplicity/stability, the Whale acts to move price *towards* belief.
        # We can calculate the exact delta_q needed to move price to P_target.
        
        b = state.liquidity_b
        
        for cid, target_p in beliefs.items():
            asset = state.assets[cid]
            current_p = state.get_asset_price(cid)
            
            # If difference is negligible, skip
            if abs(target_p - current_p) < 0.01:
                continue
                
            logging.info(f"Whale correcting {cid}: {current_p:.3f} -> {target_p:.3f}")
            
            # Inverse LMSR Price Function:
            # P = e^(q_yes/b) / (e^q_yes/b + e^q_no/b)
            # P = 1 / (1 + e^((q_no - q_yes)/b))
            # 1/P - 1 = e^((q_no - q_yes)/b)
            # ln(1/P - 1) = (q_no - q_yes)/b
            # q_yes_new - q_no = -b * ln(1/P - 1)
            # We want to change q_yes by delta. q_no stays same.
            
            # Current state: diff_old = q_yes - q_no
            # Target state: diff_new = b * ln(target_p / (1 - target_p))
            
            # Clip target_p to avoid infinity
            tp = max(0.001, min(0.999, target_p))
            
            diff_new = b * math.log(tp / (1 - tp))
            diff_old = asset.q_yes - asset.q_no
            
            # Delta needed
            delta_q_net = diff_new - diff_old
            
            # Iterate: we are buying YES shares (or selling if negative)
            trades.append((cid, delta_q_net))
            
        return trades
