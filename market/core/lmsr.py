import math

class LMSRMarket:
    """
    Implements the Logarithmic Market Scoring Rule (LMSR) for a binary market.
    """

    @staticmethod
    def cost_function(q_yes: float, q_no: float, b: float) -> float:
        """
        Calculates the cost C(q) for a given state of shares.
        Formula: C = b * ln(e^(q_yes/b) + e^(q_no/b))
        """
        if b <= 0:
            raise ValueError("Liquidity parameter b must be positive")
        
        # Use log-sum-exp trick to avoid overflow
        max_q = max(q_yes, q_no)
        return b * (max_q / b + math.log(math.exp((q_yes - max_q) / b) + math.exp((q_no - max_q) / b)))

    @staticmethod
    def current_price(q_yes: float, q_no: float, b: float) -> float:
        """
        Calculates the instantaneous price of YES shares.
        Formula: P = e^(q_yes/b) / (e^(q_yes/b) + e^(q_no/b))
        """
        if b <= 0:
            raise ValueError("Liquidity parameter b must be positive")
            
        # P = 1 / (1 + e^((q_no - q_yes)/b))
        # Derived by dividing numerator and denominator by e^(q_yes/b)
        try:
            exponent = (q_no - q_yes) / b
            # Guard against overflow in exp
            if exponent > 700: # e^700 is near max float
                return 0.0
            if exponent < -700:
                return 1.0
            
            return 1.0 / (1.0 + math.exp(exponent))
        except OverflowError:
            # Fallback if manual check fails (unlikely with bounds)
            return 0.0 if q_no > q_yes else 1.0

    @staticmethod
    def calculate_trade_cost(q_yes: float, q_no: float, b: float, delta_q: float, is_yes_share: bool) -> float:
        """
        Calculates the cost to buy delta_q shares.
        
        Args:
            q_yes, q_no: Current outstanding shares
            b: Liquidity parameter
            delta_q: Number of shares to buy (negative to sell)
            is_yes_share: True if buying YES, False if buying NO
            
        Returns:
            The cost in currency (negative means payout).
        """
        current_cost = LMSRMarket.cost_function(q_yes, q_no, b)
        
        if is_yes_share:
            new_cost = LMSRMarket.cost_function(q_yes + delta_q, q_no, b)
        else:
            new_cost = LMSRMarket.cost_function(q_yes, q_no + delta_q, b)
            
        return new_cost - current_cost

    @staticmethod
    def calculate_liquidity(whale_wealth: float, active_markets: int, min_b: float) -> float:
        """
        Calculates the dynamic liquidity parameter b_t.
        
        Formula: b_t = max(b_min, (0.5 * W_whale) / (M * ln(2)))
        
        This ensures the Whale cannot lose more than 50% of its wealth 
        even if all markets move against it completely.
        """
        if active_markets <= 0:
            return min_b
            
        # ln(2) approx 0.693147
        derived_b = (0.5 * whale_wealth) / (active_markets * math.log(2))
        return max(min_b, derived_b)
