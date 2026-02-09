from fibonacci import fib
import sys

def test():
    assert fib(0) == 0, f"Expected fib(0)=0, got {fib(0)}"
    assert fib(1) == 1, f"Expected fib(1)=1, got {fib(1)}"
    assert fib(2) == 1, f"Expected fib(2)=1, got {fib(2)}"
    assert fib(3) == 2, f"Expected fib(3)=2, got {fib(3)}"
    assert fib(4) == 3, f"Expected fib(4)=3, got {fib(4)}"
    assert fib(10) == 55, f"Expected fib(10)=55, got {fib(10)}"
    print("Tests passed!")

if __name__ == '__main__':
    try:
        test()
    except Exception as e:
        print(e)
        sys.exit(1)
