def fibonacci(n: int) -> int:
    """
    Returns the nth Fibonacci number using the fast doubling method.
    Complexity: O(log n) multiplications.

    F(0) = 0, F(1) = 1, F(n) = F(n-1) + F(n-2) for n > 1.

    Args:
        n: The index of the Fibonacci number to return. Must be a non-negative integer.

    Returns:
        The nth Fibonacci number.

    Raises:
        TypeError: If n is not an integer.
        ValueError: If n is negative.
    """
    if not isinstance(n, int):
        raise TypeError("n must be an integer")
    if n < 0:
        raise ValueError("n must be non-negative")
    if n == 0:
        return 0

    # Fast doubling method:
    # F(2k) = F(k) * (2*F(k+1) - F(k))
    # F(2k+1) = F(k+1)^2 + F(k)^2
    a, b = 0, 1
    for bit in bin(n)[2:]:
        # (a, b) = (F(k), F(k+1))
        c = a * ((b << 1) - a)
        d = a * a + b * b
        if bit == '0':
            a, b = c, d
        else:
            a, b = d, c + d
    return a

def fib(n: int) -> int:
    """Alias for fibonacci(n)."""
    return fibonacci(n)
