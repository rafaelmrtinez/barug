import time
import logging
from functools import wraps
from django.core.cache import cache
from django.db import connection

log = logging.getLogger(__name__)

def performance_monitor(func_name=None):
    """Decorator to monitor function performance"""
    def decorator(func):
        name = func_name or f"{func.__module__}.{func.__name__}"
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = (time.perf_counter() - start_time) * 1000
                log.info(f"PERF: {name} took {duration:.2f}ms")
                
                # Store performance metrics
                cache_key = f"perf_metrics_{name}"
                metrics = cache.get(cache_key, [])
                metrics.append(duration)
                if len(metrics) > 100:  # Keep last 100 measurements
                    metrics = metrics[-100:]
                cache.set(cache_key, metrics, 3600)
        
        return wrapper
    return decorator

def query_counter(func):
    """Decorator to count database queries"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        initial_queries = len(connection.queries)
        result = func(*args, **kwargs)
        query_count = len(connection.queries) - initial_queries
        log.info(f"QUERIES: {func.__name__} executed {query_count} queries")
        return result
    return wrapper

class PerformanceContext:
    """Context manager for performance monitoring"""
    def __init__(self, operation_name):
        self.operation_name = operation_name
        self.start_time = None
        
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (time.perf_counter() - self.start_time) * 1000
        log.info(f"PERF: {self.operation_name} took {duration:.2f}ms")

def get_performance_stats():
    """Get performance statistics for monitoring"""
    stats = {}
    
    # Get cache hit rates
    cache_info = cache._cache.get_stats() if hasattr(cache._cache, 'get_stats') else {}
    
    # Get database connection info
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE state = 'active';")
        active_connections = cursor.fetchone()[0]
        
        cursor.execute("SELECT count(*) FROM pg_stat_activity;")
        total_connections = cursor.fetchone()[0]
    
    stats.update({
        'cache_info': cache_info,
        'db_connections': {
            'active': active_connections,
            'total': total_connections
        }
    })
    
    return stats