from fib import fib
import unittest

class TestFibonacci(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(fib(0), 0)
        self.assertEqual(fib(1), 1)
        self.assertEqual(fib(2), 1)
        self.assertEqual(fib(3), 2)
        self.assertEqual(fib(10), 55)

    def test_negative(self):
        with self.assertRaises(ValueError):
            fib(-1)

if __name__ == "__main__":
    unittest.main()
