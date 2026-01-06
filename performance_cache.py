"""
High-Performance Caching Layer for 20+ ops/sec target
In-memory caching with TTL for frequently accessed data
"""

import time
import json
import hashlib
import logging
from typing import Dict, Any, Optional, Tuple
from threading import RLock
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class PerformanceCache:
    """
    Thread-safe high-performance cache with TTL support
    Optimized for 20+ operations/second throughput
    """
    
    def __init__(self):
        self._cache = {}
        self._timestamps = {}
        self._lock = RLock()
        self._hit_count = 0
        self._miss_count = 0
        self._eviction_count = 0
        
        # Cache TTL configurations (in seconds)
        self.ttl_config = {
            'domain_pricing': 1800,      # 30 minutes - pricing changes infrequently
            'exchange_rates': 3600,      # 1 hour - exchange rates are relatively stable
            'domain_availability': 60,   # 1 minute - availability can change quickly
            'tld_info': 3600,           # 1 hour - TLD info rarely changes
            'api_responses': 300,        # 5 minutes - generic API responses
            'database_queries': 180,     # 3 minutes - database results
            'ip_detection': 600,         # 10 minutes - IP rarely changes
            'dns_validation': 60,        # 1 minute - DNS validation can change
            'user_language': 1800,       # 30 minutes - user language preferences rarely change
            'user_data': 300,            # 5 minutes - user data for /start command optimization
        }
        
        logger.info("✅ Performance cache initialized with TTL configurations")
    
    def _generate_key(self, category: str, *args, **kwargs) -> str:
        """Generate unique cache key from category and parameters"""
        # Create deterministic key from all parameters
        key_data = {
            'category': category,
            'args': args,
            'kwargs': sorted(kwargs.items()) if kwargs else {}
        }
        key_string = json.dumps(key_data, sort_keys=True, default=str)
        key_hash = hashlib.md5(key_string.encode()).hexdigest()[:16]
        return f"{category}:{key_hash}"
    
    def get(self, key: str, category: str, *args, **kwargs) -> Optional[Any]:
        """Get cached value if valid"""
        cache_key = key if ':' in key else self._generate_key(category, *args, **kwargs)
        current_time = time.time()
        
        with self._lock:
            if cache_key in self._cache:
                timestamp = self._timestamps.get(cache_key, 0)
                ttl = self.ttl_config.get(category, 300)
                
                if current_time - timestamp < ttl:
                    # Cache hit
                    self._hit_count += 1
                    value = self._cache[cache_key]
                    logger.debug(f"💾 Cache HIT: {category} (age: {current_time - timestamp:.1f}s)")
                    return value
                else:
                    # Cache expired
                    self._evict_entry(cache_key)
                    logger.debug(f"⏰ Cache EXPIRED: {category} (age: {current_time - timestamp:.1f}s)")
            
            # Cache miss
            self._miss_count += 1
            logger.debug(f"❌ Cache MISS: {category}")
            return None
    
    def set(self, key: str, value: Any, category: str, ttl: Optional[int] = None, *args, **kwargs) -> None:
        """Cache value with TTL"""
        cache_key = key if ':' in key else self._generate_key(category, *args, **kwargs)
        current_time = time.time()
        effective_ttl = ttl or self.ttl_config.get(category, 300)
        
        with self._lock:
            self._cache[cache_key] = value
            self._timestamps[cache_key] = current_time
            logger.debug(f"💾 Cache SET: {category} (TTL: {effective_ttl}s)")
    
    def invalidate(self, category: str, *args, **kwargs) -> bool:
        """Invalidate specific cache entry"""
        cache_key = self._generate_key(category, *args, **kwargs)
        
        with self._lock:
            if cache_key in self._cache:
                self._evict_entry(cache_key)
                logger.debug(f"🗑️ Cache INVALIDATED: {category}")
                return True
            return False
    
    def invalidate_key(self, key: str, category: str) -> bool:
        """Invalidate cache entry by direct key"""
        with self._lock:
            if key in self._cache:
                self._evict_entry(key)
                logger.debug(f"🗑️ Cache KEY INVALIDATED: {key}")
                return True
            return False
    
    def invalidate_category(self, category: str) -> int:
        """Invalidate all entries in a category"""
        keys_to_remove = []
        
        with self._lock:
            for key in self._cache.keys():
                if key.startswith(f"{category}:"):
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                self._evict_entry(key)
            
            count = len(keys_to_remove)
            if count > 0:
                logger.info(f"🗑️ Cache CATEGORY INVALIDATED: {category} ({count} entries)")
            return count
    
    def _evict_entry(self, cache_key: str) -> None:
        """Remove entry from cache"""
        self._cache.pop(cache_key, None)
        self._timestamps.pop(cache_key, None)
        self._eviction_count += 1
    
    def cleanup_expired(self) -> int:
        """Clean up all expired entries"""
        current_time = time.time()
        keys_to_remove = []
        
        with self._lock:
            for cache_key, timestamp in self._timestamps.items():
                category = cache_key.split(':', 1)[0]
                ttl = self.ttl_config.get(category, 300)
                
                if current_time - timestamp >= ttl:
                    keys_to_remove.append(cache_key)
            
            for key in keys_to_remove:
                self._evict_entry(key)
            
            count = len(keys_to_remove)
            if count > 0:
                logger.debug(f"🧹 Cache cleanup: removed {count} expired entries")
            return count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        with self._lock:
            total_requests = self._hit_count + self._miss_count
            hit_rate = (self._hit_count / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'total_entries': len(self._cache),
                'total_requests': total_requests,
                'cache_hits': self._hit_count,
                'cache_misses': self._miss_count,
                'hit_rate_percent': hit_rate,
                'evictions': self._eviction_count,
                'categories': list(self.ttl_config.keys())
            }
    
    def clear(self) -> None:
        """Clear all cache entries"""
        with self._lock:
            entry_count = len(self._cache)
            self._cache.clear()
            self._timestamps.clear()
            logger.info(f"🗑️ Cache cleared: {entry_count} entries removed")

# Global high-performance cache instance
_performance_cache = PerformanceCache()

# Export for external imports
performance_cache = _performance_cache

# Convenience functions for external use
def cache_get(category: str, *args, **kwargs) -> Optional[Any]:
    """Get value from performance cache"""
    # Fix API mismatch: PerformanceCache.get expects (key, category, ...) but we pass (category, ...)
    # Generate a cache key from category and args to match expected signature
    cache_key = _performance_cache._generate_key(category, *args, **kwargs)
    return _performance_cache.get(cache_key, category, *args, **kwargs)

def cache_set(category: str, value: Any, *args, **kwargs) -> None:
    """Set value in performance cache"""
    # Fix API mismatch: PerformanceCache.set expects (key, value, category, ...) but we pass (category, value, ...)
    cache_key = _performance_cache._generate_key(category, *args, **kwargs) 
    _performance_cache.set(cache_key, value, category, *args, **kwargs)

def cache_invalidate(category: str, *args, **kwargs) -> bool:
    """Invalidate cache entry"""
    return _performance_cache.invalidate(category, *args, **kwargs)

def cache_invalidate_category(category: str) -> int:
    """Invalidate entire category"""
    return _performance_cache.invalidate_category(category)

def cache_cleanup() -> int:
    """Clean up expired entries"""
    return _performance_cache.cleanup_expired()

def cache_stats() -> Dict[str, Any]:
    """Get cache statistics"""
    return _performance_cache.get_stats()

def cache_clear() -> None:
    """Clear all cache"""
    _performance_cache.clear()

# Scheduled cleanup function
async def scheduled_cache_cleanup():
    """Scheduled cache cleanup for async environments"""
    try:
        cleaned = cache_cleanup()
        if cleaned > 0:
            logger.info(f"🧹 Scheduled cache cleanup: removed {cleaned} expired entries")
    except Exception as e:
        logger.warning(f"⚠️ Cache cleanup error: {e}")

logger.info("✅ Performance cache module loaded - ready for 20+ ops/sec caching")