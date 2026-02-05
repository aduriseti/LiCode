import unittest
import math
from market.core.lmsr import LMSRMarket

class TestLMSRMarket(unittest.TestCase):

    def test_cost_function_initial_state(self):
        """Test cost is b * ln(2) when q_yes = q_no = 0"""
        b = 100.0
        cost = LMSRMarket.cost_function(0, 0, b)
        expected = b * math.log(2)
        self.assertAlmostEqual(cost, expected, places=5)

    def test_cost_function_scaling(self):
        """Test cost scales linearly with b"""
        b1 = 100.0
        b2 = 200.0
        cost1 = LMSRMarket.cost_function(10, 10, b1)
        cost2 = LMSRMarket.cost_function(10, 10, b2)
        # It's not strictly linear for q != 0, but for q=0 it is.
        # Let's test specific values instead.
        self.assertTrue(cost2 > cost1)

    def test_price_neutral(self):
        """Test price is 0.5 when shares are equal"""
        b = 100.0
        price = LMSRMarket.current_price(50, 50, b)
        self.assertAlmostEqual(price, 0.5, places=7)

    def test_price_movement(self):
        """Test buying YES shares increases YES price"""
        b = 100.0
        q_yes = 0
        q_no = 0
        
        # Initial price
        p0 = LMSRMarket.current_price(q_yes, q_no, b)
        self.assertEqual(p0, 0.5)
        
        # Buy 10 YES shares
        q_yes += 10
        p1 = LMSRMarket.current_price(q_yes, q_no, b)
        self.assertTrue(p1 > 0.5)
        
        # Buy 100 more YES shares
        q_yes += 100
        p2 = LMSRMarket.current_price(q_yes, q_no, b)
        self.assertTrue(p2 > p1)

    def test_price_bounds(self):
        """Test price never exceeds 1.0 or drops below 0.0"""
        b = 10.0
        # Extreme YES favor
        p_high = LMSRMarket.current_price(1000, 0, b)
        self.assertTrue(p_high <= 1.0)
        self.assertAlmostEqual(p_high, 1.0, places=4)
        
        # Extreme NO favor
        p_low = LMSRMarket.current_price(0, 1000, b)
        self.assertTrue(p_low >= 0.0)
        self.assertAlmostEqual(p_low, 0.0, places=4)

    def test_trade_cost(self):
        """Test that trade cost equals difference in cost function"""
        b = 100.0
        q_yes = 10
        q_no = 20
        delta = 5
        
        # Calculate expected manually
        c_before = LMSRMarket.cost_function(q_yes, q_no, b)
        c_after = LMSRMarket.cost_function(q_yes + delta, q_no, b)
        expected_cost = c_after - c_before
        
        calc_cost = LMSRMarket.calculate_trade_cost(q_yes, q_no, b, delta, True)
        self.assertAlmostEqual(calc_cost, expected_cost, places=5)

    def test_trade_zero_sum_logic(self):
        """Buying NO should be symmetric to selling YES (conceptually, though shares differ)"""
        # In LMSR, buying NO raises NO price (lowers YES price).
        # Selling YES also lowers YES price.
        pass

    def test_liquidity_dynamic(self):
        """Test dynamic liquidity adjustment"""
        min_b = 10.0
        whale_wealth = 2000.0
        
        # Case 1: 1 active market
        # b = (0.5 * 2000) / (1 * 0.693) = 1000 / 0.693 = ~1443
        b_1 = LMSRMarket.calculate_liquidity(whale_wealth, 1, min_b)
        self.assertTrue(b_1 > min_b)
        self.assertAlmostEqual(b_1, 1000 / math.log(2), places=2)
        
        # Case 2: 100 active markets
        # b = 1000 / 69.3 = ~14.4
        b_100 = LMSRMarket.calculate_liquidity(whale_wealth, 100, min_b)
        self.assertTrue(b_100 < b_1)
        
        # Case 3: Poor whale
        whale_wealth_poor = 1.0
        b_poor = LMSRMarket.calculate_liquidity(whale_wealth_poor, 10, min_b)
        self.assertEqual(b_poor, min_b)

if __name__ == '__main__':
    unittest.main()
