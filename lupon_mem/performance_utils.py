import time
import logging
from functools import wraps
from django.core.cache import cache

logger = logging.getLogger(__name__)

def performance_monitor(func_name=None):
    """Decorator to monitor function performance"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                # Log performance
                name = func_name or func.__name__
                logger.info(f"Performance: {name} executed in {execution_time:.3f}s")
                
                # Store in cache for monitoring
                cache.set(f"perf_{name}_last", execution_time, 3600)
                
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(f"Performance: {func_name or func.__name__} failed after {execution_time:.3f}s: {e}")
                raise
                
        return wrapper
    return decorator

def get_performance_stats():
    """Get recent performance statistics"""
    stats = {}
    for key in cache.keys("perf_*_last"):
        func_name = key.replace("perf_", "").replace("_last", "")
        stats[func_name] = cache.get(key)
    return stats