"""
Real-time Performance Monitoring for 20+ ops/sec target
Tracks throughput, response times, and system metrics
"""

import time
import logging
import asyncio
from typing import Dict, List, Optional, Any
from collections import deque
from threading import RLock
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """
    Real-time performance monitoring for high-throughput operations
    Tracks ops/sec, response times, and resource utilization
    """
    
    def __init__(self, window_size_seconds: int = 60):
        self.window_size = window_size_seconds
        self._operations = deque()  # (timestamp, operation_type, duration)
        self._lock = RLock()
        self._start_time = time.time()
        
        # Operation counters
        self._operation_counts = {}
        self._total_operations = 0
        self._total_duration = 0.0
        
        # Response time tracking
        self._response_times = deque(maxlen=1000)  # Last 1000 operations
        
        # Error tracking
        self._error_counts = {}
        self._total_errors = 0
        
        logger.info("✅ Performance monitor initialized for throughput tracking")
    
    def start_operation(self, operation_type: str) -> Dict[str, Any]:
        """Start timing an operation"""
        return {
            'operation_type': operation_type,
            'start_time': time.time(),
            'monitor': self
        }
    
    def end_operation(self, operation_context: Dict[str, Any], success: bool = True, error_type: Optional[str] = None) -> None:
        """End timing an operation and record metrics"""
        end_time = time.time()
        start_time = operation_context['start_time']
        operation_type = operation_context['operation_type']
        duration = end_time - start_time
        
        with self._lock:
            # Record operation
            self._operations.append((end_time, operation_type, duration, success))
            self._operation_counts[operation_type] = self._operation_counts.get(operation_type, 0) + 1
            self._total_operations += 1
            self._total_duration += duration
            
            # Record response time
            self._response_times.append(duration)
            
            # Record errors
            if not success and error_type:
                self._error_counts[error_type] = self._error_counts.get(error_type, 0) + 1
                self._total_errors += 1
            
            # Clean old operations outside window
            self._cleanup_old_operations(end_time)
            
            # Log slow operations
            if duration > 5.0:  # Operations taking more than 5 seconds
                logger.warning(f"⚠️ SLOW OPERATION: {operation_type} took {duration:.2f}s")
            elif duration > 2.0:
                logger.info(f"🐌 SLOW: {operation_type} took {duration:.2f}s")
    
    def _cleanup_old_operations(self, current_time: float) -> None:
        """Remove operations outside the time window"""
        cutoff_time = current_time - self.window_size
        while self._operations and self._operations[0][0] < cutoff_time:
            self._operations.popleft()
    
    def get_throughput_metrics(self) -> Dict[str, Any]:
        """Get current throughput metrics"""
        current_time = time.time()
        
        with self._lock:
            self._cleanup_old_operations(current_time)
            
            # Calculate metrics for current window
            window_operations = len(self._operations)
            window_duration = min(self.window_size, current_time - self._start_time)
            
            ops_per_second = window_operations / window_duration if window_duration > 0 else 0
            
            # Calculate response time statistics
            if self._response_times:
                response_times = list(self._response_times)
                avg_response_time = sum(response_times) / len(response_times)
                min_response_time = min(response_times)
                max_response_time = max(response_times)
                
                # Calculate percentiles
                sorted_times = sorted(response_times)
                p50 = sorted_times[len(sorted_times) // 2] if sorted_times else 0
                p95 = sorted_times[int(len(sorted_times) * 0.95)] if sorted_times else 0
                p99 = sorted_times[int(len(sorted_times) * 0.99)] if sorted_times else 0
            else:
                avg_response_time = min_response_time = max_response_time = 0
                p50 = p95 = p99 = 0
            
            # Operation type breakdown
            operation_breakdown = {}
            for timestamp, op_type, duration, success in self._operations:
                if op_type not in operation_breakdown:
                    operation_breakdown[op_type] = {'count': 0, 'total_duration': 0, 'successes': 0}
                operation_breakdown[op_type]['count'] += 1
                operation_breakdown[op_type]['total_duration'] += duration
                if success:
                    operation_breakdown[op_type]['successes'] += 1
            
            # Calculate success rates
            for op_type, stats in operation_breakdown.items():
                stats['success_rate'] = (stats['successes'] / stats['count'] * 100) if stats['count'] > 0 else 0
                stats['avg_duration'] = stats['total_duration'] / stats['count'] if stats['count'] > 0 else 0
            
            return {
                'current_ops_per_second': ops_per_second,
                'window_operations': window_operations,
                'window_duration_seconds': window_duration,
                'total_operations': self._total_operations,
                'total_errors': self._total_errors,
                'error_rate_percent': (self._total_errors / self._total_operations * 100) if self._total_operations > 0 else 0,
                'response_times': {
                    'average_ms': avg_response_time * 1000,
                    'min_ms': min_response_time * 1000,
                    'max_ms': max_response_time * 1000,
                    'p50_ms': p50 * 1000,
                    'p95_ms': p95 * 1000,
                    'p99_ms': p99 * 1000
                },
                'operation_breakdown': operation_breakdown,
                'target_ops_per_second': 20,
                'target_achieved': ops_per_second >= 20
            }
    
    def log_performance_summary(self) -> None:
        """Log a performance summary"""
        metrics = self.get_throughput_metrics()
        
        ops_per_sec = metrics['current_ops_per_second']
        target_achieved = "✅ TARGET ACHIEVED" if metrics['target_achieved'] else "⚠️ BELOW TARGET"
        
        logger.info(f"📊 PERFORMANCE METRICS ({target_achieved}):")
        logger.info(f"   • Current throughput: {ops_per_sec:.1f} ops/sec (target: 20 ops/sec)")
        logger.info(f"   • Window operations: {metrics['window_operations']} operations")
        logger.info(f"   • Average response time: {metrics['response_times']['average_ms']:.1f}ms")
        logger.info(f"   • P95 response time: {metrics['response_times']['p95_ms']:.1f}ms")
        logger.info(f"   • Success rate: {100 - metrics['error_rate_percent']:.1f}%")
        
        # Log operation breakdown
        for op_type, stats in metrics['operation_breakdown'].items():
            logger.info(f"   • {op_type}: {stats['count']} ops, {stats['avg_duration']*1000:.1f}ms avg, {stats['success_rate']:.1f}% success")

# Global performance monitor instance
_performance_monitor = PerformanceMonitor()

# Convenience functions for external use
def start_operation_timer(operation_type: str) -> Dict[str, Any]:
    """Start timing an operation"""
    return _performance_monitor.start_operation(operation_type)

def end_operation_timer(operation_context: Dict[str, Any], success: bool = True, error_type: Optional[str] = None) -> None:
    """End timing an operation"""
    _performance_monitor.end_operation(operation_context, success, error_type)

def get_performance_metrics() -> Dict[str, Any]:
    """Get current performance metrics"""
    return _performance_monitor.get_throughput_metrics()

def log_performance_summary() -> None:
    """Log performance summary"""
    _performance_monitor.log_performance_summary()

def log_error_event(error_type: str, context: Dict[str, Any]) -> None:
    """Log an error event for performance monitoring"""
    try:
        logger.error(f"🚨 ERROR EVENT: {error_type}")
        if context:
            for key, value in context.items():
                logger.error(f"   • {key}: {value}")
        
        # Record error in performance monitor
        with _performance_monitor._lock:
            _performance_monitor._error_counts[error_type] = _performance_monitor._error_counts.get(error_type, 0) + 1
            _performance_monitor._total_errors += 1
            
    except Exception as e:
        # Prevent error logging from causing more errors
        logger.critical(f"💥 ERROR EVENT LOGGING FAILURE: {e}")

# Async context manager for easy operation timing
class OperationTimer:
    """Context manager for timing operations"""
    
    def __init__(self, operation_type: str):
        self.operation_type = operation_type
        self.context = None
    
    async def __aenter__(self):
        self.context = start_operation_timer(self.operation_type)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        success = exc_type is None
        error_type = exc_type.__name__ if exc_type else None
        if self.context is not None:
            end_operation_timer(self.context, success, error_type)

# Decorator for automatic operation timing
def monitor_performance(operation_type: str):
    """Decorator to automatically monitor operation performance"""
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                async with OperationTimer(operation_type):
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
                context = start_operation_timer(operation_type)
                try:
                    result = func(*args, **kwargs)
                    end_operation_timer(context, success=True)
                    return result
                except Exception as e:
                    end_operation_timer(context, success=False, error_type=type(e).__name__)
                    raise
            return sync_wrapper
    return decorator

logger.info("✅ Performance monitoring module loaded - ready for 20+ ops/sec tracking")