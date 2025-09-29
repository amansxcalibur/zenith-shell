import functools
import time

def timing_decorator(func):
    """Decorator to log execution time of functions"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            end_time = time.perf_counter()
            execution_time = (end_time - start_time) * 1000  # milliseconds
            print(f"[TIMING] {func.__name__}: {execution_time:.2f}ms")
            return result
        except Exception as e:
            end_time = time.perf_counter()
            execution_time = (end_time - start_time) * 1000
            print(f"[TIMING] {func.__name__}: {execution_time:.2f}ms (FAILED: {e})")
            raise
    return wrapper