from typing import Dict, List, Tuple
from .state import MarketState
from .lmsr import LMSRMarket

class Strategy:
    """
    Converts agent beliefs into LMSR trades using a heuristic Kelly criterion.
    """
    
    @staticmethod
    def beliefs_to_trades(
        beliefs: Dict[str, float],
        wealth: float,
        state: MarketState
    ) -> List[Tuple[str, float]]:
        """
        Calculates optimal trades given current beliefs and prices.
        
        Args:
            beliefs: dict {asset_id: probability} (0.0 to 1.0)
            wealth: Agent's current wealth
            state: Current market state
            
        Returns:
            List of (asset_id, delta_q)
        """
        trades = []
        b = state.liquidity_b
        
        # 1. Clip beliefs and compute ideal fractions
        epsilon = 0.01
        desired_exposures = {}
        total_exposure = 0.0
        
        for aid, belief in beliefs.items():
            # Skip if asset not in market
            if aid not in state.assets:
                continue
                
            price = state.get_asset_price(aid)
            
            # 1. Clip belief (Design 4.D Step 1: epsilon = 0.01)
            p_belief = max(epsilon, min(1.0 - epsilon, belief))
            
            # 2. Clip price for denominator safety (Design 4.D Step 2)
            p_safe = max(epsilon, min(1.0 - epsilon, price))
            
            # Kelly fraction: f* = (p_belief - price) / (price * (1 - price))
            # If p_belief > price, we go long. If p_belief < price, we go short.
            f_star = (p_belief - price) / (p_safe * (1.0 - p_safe))
            
            # Record absolute exposure for normalization
            desired_exposures[aid] = f_star
            total_exposure += abs(f_star)
            
        # 2. Normalize to avoid leverage (sum of absolute exposures <= 1.0)
        # If total_exposure > 1, scale everything down.
        scale = 1.0
        if total_exposure > 1.0:
            scale = 1.0 / total_exposure
            
        # 3. Calculate delta_q for each trade
        for aid, f_star in desired_exposures.items():
            f_final = f_star * scale
            wager = wealth * f_final # Positive (long) or negative (short)
            
            asset = state.assets[aid]
            b = state.liquidity_b
            
            # Use exact inverse cost function to determine shares for wager
            if wager >= 0:
                # Buying YES shares
                delta_q = LMSRMarket.calculate_delta_q(
                    asset.q_yes, asset.q_no, b, wager, is_yes_share=True
                )
            else:
                # Buying NO shares (Shorting YES)
                # We spend abs(wager) to buy NO shares
                delta_q_no = LMSRMarket.calculate_delta_q(
                    asset.q_yes, asset.q_no, b, abs(wager), is_yes_share=False
                )
                # In our convention, delta_q < 0 means buying NO shares
                delta_q = -delta_q_no
            
            # Cap delta_q to avoid moving market too wildly in one go
            if abs(delta_q) > 1000: 
                delta_q = 1000 * (1 if delta_q > 0 else -1)
                
            trades.append((aid, delta_q))
            
        return trades
