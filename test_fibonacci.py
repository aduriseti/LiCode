from fibonacci import fibonacci, fib

def test_fibonacci():
    assert fibonacci(0) == 0
    assert fibonacci(1) == 1
    assert fibonacci(2) == 1
    assert fibonacci(3) == 2
    assert fibonacci(4) == 3
    assert fibonacci(5) == 5
    assert fibonacci(6) == 8
    assert fibonacci(10) == 55
    print("fibonacci tests passed!")

def test_fib():
    assert fib(0) == 0
    assert fib(1) == 1
    assert fib(10) == 55
    print("fib tests passed!")

if __name__ == "__main__":
    test_fibonacci()
    test_fib()
