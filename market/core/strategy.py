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
            
            # Clip belief
            p_belief = max(epsilon, min(1.0 - epsilon, belief))
            
            # Kelly fraction: f* = (p - price) / (price * (1 - price))
            # Note: This is a simplified Kelly for binary options.
            # If p > price, we go long. If p < price, we go short.
            # The denominator approaches 0 if price is extreme, so clamp it.
            price_safe = max(0.01, min(0.99, price))
            
            f_star = (p_belief - price) / (price_safe * (1.0 - price_safe))
            
            # Record absolute exposure for normalization
            desired_exposures[aid] = f_star
            total_exposure += abs(f_star)
            
        # 2. Normalize to avoid leverage (sum of absolute exposures <= 1.0)
        # If total_exposure > 1, scale everything down.
        scale = 1.0
        if total_exposure > 1.0:
            scale = 1.0 / total_exposure
            
        # 3. Calculate delta_q for each trade
        # We want to spend `wealth * f_star * scale` on this trade?
        # No, Kelly fraction f* is fraction of wealth to WAGER.
        # In LMSR, cost ~ delta_q * price (roughly).
        # Exact mapping from "fraction of wealth" to "delta_q" in LMSR is complex.
        # Approximation: Cost ~= delta_q * price.
        # So delta_q ~= (Wealth * f_star) / price.
        
        for aid, f_star in desired_exposures.items():
            f_final = f_star * scale
            wager = wealth * f_final # Positive (long) or negative (short)
            
            price = state.get_asset_price(aid)
            price_safe = max(0.01, min(0.99, price))
            
            # Approx delta_q
            # If Long: buying shares at ~price. Shares = Wager / Price
            # If Short: selling shares (buying NO). Cost is similar.
            
            # Refined approx using the log-price derivative:
            # We want to move price towards belief? 
            # Or just invest specific amount?
            # Let's stick to the "Spend $X" logic.
            
            delta_q = wager / price_safe
            
            # Cap delta_q to avoid moving market too wildy in one go
            # (Safety clamp)
            if abs(delta_q) > 1000: 
                delta_q = 1000 * (1 if delta_q > 0 else -1)
                
            trades.append((aid, delta_q))
            
        return trades
