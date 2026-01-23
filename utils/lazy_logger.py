"""
Lazy Logger - Performance-optimized logging utilities

This module provides lazy formatting for log messages to avoid
string construction overhead when log level is disabled.

Usage:
    from utils.lazy_logger import get_lazy_logger
    
    logger = get_lazy_logger(__name__)
    
    # These use lazy formatting (no string construction if level disabled)
    logger.debug("Processing %s with value %s", item_id, value)
    logger.info("User %s performed action %s", user_id, action)
    
    # For complex objects, use lambdas
    logger.debug_lazy(lambda: f"Complex object: {expensive_computation()}")
"""

import logging
from typing import Callable, Any
from functools import wraps


class LazyLogger:
    """
    Wrapper around standard logger with lazy evaluation support.
    
    Provides:
    - Standard logging methods with lazy % formatting
    - debug_lazy/info_lazy methods for lambda-based lazy evaluation
    - Performance-optimized checks before string construction
    """
    
    def __init__(self, logger: logging.Logger):
        self._logger = logger
    
    @property
    def level(self):
        return self._logger.level
    
    def isEnabledFor(self, level: int) -> bool:
        return self._logger.isEnabledFor(level)
    
    # Standard methods - use % formatting for lazy evaluation
    def debug(self, msg: str, *args, **kwargs):
        """Log debug message with lazy % formatting"""
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug(msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        """Log info message with lazy % formatting"""
        if self._logger.isEnabledFor(logging.INFO):
            self._logger.info(msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        """Log warning message - always evaluated"""
        self._logger.warning(msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        """Log error message - always evaluated"""
        self._logger.error(msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        """Log exception with traceback - always evaluated"""
        self._logger.exception(msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        """Log critical message - always evaluated"""
        self._logger.critical(msg, *args, **kwargs)
    
    # Lazy lambda methods for complex expressions
    def debug_lazy(self, msg_func: Callable[[], str]):
        """
        Log debug message using lazy lambda evaluation.
        
        The lambda is only called if debug level is enabled.
        
        Example:
            logger.debug_lazy(lambda: f"Heavy computation: {expensive_func()}")
        """
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug(msg_func())
    
    def info_lazy(self, msg_func: Callable[[], str]):
        """Log info message using lazy lambda evaluation"""
        if self._logger.isEnabledFor(logging.INFO):
            self._logger.info(msg_func())
    
    # Passthrough for standard logger attributes
    def setLevel(self, level):
        self._logger.setLevel(level)
    
    def addHandler(self, handler):
        self._logger.addHandler(handler)
    
    def removeHandler(self, handler):
        self._logger.removeHandler(handler)
    
    @property
    def handlers(self):
        return self._logger.handlers
    
    @property
    def name(self):
        return self._logger.name


def get_lazy_logger(name: str) -> LazyLogger:
    """
    Get a lazy logger for the given module name.
    
    Args:
        name: Module name (typically __name__)
        
    Returns:
        LazyLogger instance wrapping the standard logger
    """
    return LazyLogger(logging.getLogger(name))


# Cache of lazy loggers
_lazy_loggers: dict = {}


def get_cached_lazy_logger(name: str) -> LazyLogger:
    """Get or create a cached lazy logger"""
    if name not in _lazy_loggers:
        _lazy_loggers[name] = LazyLogger(logging.getLogger(name))
    return _lazy_loggers[name]


# Decorator for logging function calls
def log_function_call(logger: LazyLogger, level: str = 'debug'):
    """
    Decorator to log function entry and exit.
    
    Usage:
        @log_function_call(logger)
        async def my_function(arg1, arg2):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            func_name = func.__name__
            if level == 'debug':
                logger.debug("Entering %s", func_name)
            else:
                logger.info("Entering %s", func_name)
            
            try:
                result = await func(*args, **kwargs)
                if level == 'debug':
                    logger.debug("Exiting %s", func_name)
                return result
            except Exception as e:
                logger.error("Error in %s: %s", func_name, str(e))
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            func_name = func.__name__
            if level == 'debug':
                logger.debug("Entering %s", func_name)
            else:
                logger.info("Entering %s", func_name)
            
            try:
                result = func(*args, **kwargs)
                if level == 'debug':
                    logger.debug("Exiting %s", func_name)
                return result
            except Exception as e:
                logger.error("Error in %s: %s", func_name, str(e))
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


# Performance monitoring decorator
def timed_operation(logger: LazyLogger, operation_name: str = None):
    """
    Decorator to time and log operation duration.
    
    Usage:
        @timed_operation(logger, "database_query")
        async def fetch_data():
            ...
    """
    def decorator(func):
        import time
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                op_name = operation_name or func.__name__
                logger.debug("⏱️ %s completed in %.2fms", op_name, elapsed)
                return result
            except Exception as e:
                elapsed = (time.perf_counter() - start) * 1000
                op_name = operation_name or func.__name__
                logger.error("⏱️ %s failed after %.2fms: %s", op_name, elapsed, str(e))
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                op_name = operation_name or func.__name__
                logger.debug("⏱️ %s completed in %.2fms", op_name, elapsed)
                return result
            except Exception as e:
                elapsed = (time.perf_counter() - start) * 1000
                op_name = operation_name or func.__name__
                logger.error("⏱️ %s failed after %.2fms: %s", op_name, elapsed, str(e))
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
