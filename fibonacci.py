def fib(n):
    if n < 0:
        raise ValueError("n must be a non-negative integer")
    if n == 0:
        return 0
    if n == 1:
        return 1

    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        try:
            n = int(sys.argv[1])
            print(fib(n))
        except ValueError:
            print("Please provide an integer argument")
