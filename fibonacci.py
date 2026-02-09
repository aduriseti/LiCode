def fibonacci(n):
    """Returns the nth Fibonacci number."""
    if n < 0:
        raise ValueError("n must be non-negative")
    if n == 0:
        return 0
    if n == 1:
        return 1
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

if __name__ == "__main__":
    # Simple test cases
    test_cases = {0: 0, 1: 1, 2: 1, 3: 2, 4: 3, 5: 5, 10: 55}
    for n, expected in test_cases.items():
        result = fibonacci(n)
        assert result == expected, f"fibonacci({n}) expected {expected}, got {result}"
    print("All tests passed!")
