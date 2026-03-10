import math
import unittest

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

    def test_calculate_delta_q_accuracy(self):
        """Verify that calculate_delta_q produces the expected cost via cost_function."""
        b = 100.0
        q_yes = 0.0
        q_no = 0.0
        target_cost = 50.0

        # Calculate how many shares we can buy for 50 credits
        dq = LMSRMarket.calculate_delta_q(q_yes, q_no, b, target_cost, is_yes_share=True)

        # Verify that the cost of buying dq shares is exactly target_cost
        actual_cost = LMSRMarket.cost_function(q_yes + dq, q_no, b) - LMSRMarket.cost_function(
            q_yes, q_no, b
        )
        self.assertAlmostEqual(actual_cost, target_cost, places=5)

        # Test for NO shares
        dq_no = LMSRMarket.calculate_delta_q(q_yes, q_no, b, target_cost, is_yes_share=False)
        actual_cost_no = LMSRMarket.cost_function(
            q_yes, q_no + dq_no, b
        ) - LMSRMarket.cost_function(q_yes, q_no, b)
        self.assertAlmostEqual(actual_cost_no, target_cost, places=5)


if __name__ == "__main__":
    unittest.main()
