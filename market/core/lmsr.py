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
    def calculate_delta_q(q_yes: float, q_no: float, b: float, cost: float, is_yes_share: bool) -> float:
        """
        Calculates the exact delta_q needed for a specific cost.
        Derived from inverting the cost function:
        Cost = b * ln( (e^((q_yes+dq)/b) + e^(q_no/b)) / (e^(q_yes/b) + e^(q_no/b)) )
        
        Args:
            q_yes, q_no: Current shares
            b: Liquidity
            cost: Amount to spend (must be positive to buy)
            is_yes_share: Direction
            
        Returns:
            The number of shares that results in this exact cost.
        """
        if b <= 0:
            raise ValueError("Liquidity parameter b must be positive")
        
        # We use the relationship: 
        # e^(Cost/b) = (e^(new_q/b) + e^(fixed_q/b)) / (e^(old_q/b) + e^(fixed_q/b))
        
        fixed_q = q_no if is_yes_share else q_yes
        old_q = q_yes if is_yes_share else q_no
        
        # e^(Cost/b) * (e^(old_q/b) + e^(fixed_q/b)) = e^(new_q/b) + e^(fixed_q/b)
        # e^(new_q/b) = e^(Cost/b) * (e^(old_q/b) + e^(fixed_q/b)) - e^(fixed_q/b)
        
        # Use log-sum-exp trick for stability
        # let term1 = Cost/b + ln(e^(old_q/b) + e^(fixed_q/b))
        # let term2 = fixed_q/b
        # new_q/b = ln(e^term1 - e^term2)
        
        max_q_inner = max(old_q, fixed_q)
        ln_sum_exp = max_q_inner / b + math.log(math.exp((old_q - max_q_inner) / b) + math.exp((fixed_q - max_q_inner) / b))
        
        term1 = cost / b + ln_sum_exp
        term2 = fixed_q / b
        
        # ln(e^t1 - e^t2) = t1 + ln(1 - e^(t2-t1))
        # Safety check: if term2 >= term1, the log is undefined (spent too much)
        # but Kelly ensures cost is within budget relative to b.
        try:
            diff = term2 - term1
            if diff >= 0:
                 # This would mean the purchase is impossible (infinite price)
                 return 1000.0 # Return cap
            
            new_q_over_b = term1 + math.log(1.0 - math.exp(diff))
            new_q = new_q_over_b * b
            return new_q - old_q
        except (ValueError, OverflowError):
            return 1000.0

    @staticmethod
    def calculate_payout(q_agent: float, q_yes_pool: float, q_no_pool: float, b: float) -> float:
        """
        Calculates the credit value of q_agent shares if they were sold back to the pool.
        This is the difference in the cost function if the pool's shares were reduced by q_agent.
        Formula: Cost(Q_pool) - Cost(Q_pool - q_agent)
        """
        if abs(q_agent) < 1e-9:
            return 0.0
            
        current_cost = LMSRMarket.cost_function(q_yes_pool, q_no_pool, b)
        
        # If agent owns q_agent 'net' shares, it means they have a claim on the YES pool
        # (if q_agent > 0) or the NO pool (if q_agent < 0).
        if q_agent > 0:
            # Payout for selling YES shares
            reduced_cost = LMSRMarket.cost_function(q_yes_pool - q_agent, q_no_pool, b)
        else:
            # Payout for selling NO shares (q_agent is negative, so we subtract it)
            reduced_cost = LMSRMarket.cost_function(q_yes_pool, q_no_pool + q_agent, b)
            
        return current_cost - reduced_cost
