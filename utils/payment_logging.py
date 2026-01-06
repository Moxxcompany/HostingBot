#!/usr/bin/env python3
"""
Centralized Payment Logging Utilities
Comprehensive logging for payment state transitions, failures, and operational visibility

Features:
- Payment state transition audit trail
- Performance metrics for payment operations  
- Enhanced error logging with actionable context
- Integration with existing structured logging system
- Correlation IDs for multi-step payment flows
- Provider-specific API call logging
- Webhook processing event tracking
"""

import logging
import time
import json
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
from decimal import Decimal
from dataclasses import dataclass, asdict, field
from enum import Enum
from contextvars import ContextVar

# Import existing production logging system - with fallbacks built-in
try:
    from monitoring.production_logging import (
        get_production_logger,  # type: ignore
        LogLevel as ProdLogLevel, 
        MetricType, 
        log_performance_metric, 
        log_error_with_context
    )
    PRODUCTION_LOGGING_AVAILABLE = True
except ImportError:
    PRODUCTION_LOGGING_AVAILABLE = False
    # Create robust fallback functions to prevent unbound errors
    
    class MockProductionLogger:
        def log_structured(self, level, component: str, message: str, context: Optional[Dict] = None, trace_id: Optional[str] = None, user_id: Optional[int] = None, order_id: Optional[str] = None):
            pass
    
    def get_production_logger() -> MockProductionLogger:
        return MockProductionLogger()
    
    ProdLogLevel = type('ProdLogLevel', (), {
        'DEBUG': "DEBUG",
        'INFO': "INFO", 
        'WARNING': "WARNING",
        'ERROR': "ERROR",
        'CRITICAL': "CRITICAL"
    })
    
    def log_performance_metric(component: str, operation: str, duration_ms: float, success: bool = True) -> None:
        pass
    
    def log_error_with_context(component: str, error: Exception, context: Dict[str, Any], user_id: Optional[int] = None, order_id: Optional[str] = None) -> None:
        pass

# Import admin alerts for critical payment issues - with fallbacks built-in
try:
    from admin_alerts import (
        send_critical_alert, 
        send_error_alert, 
        AlertCategory as AdminAlertCategory  # type: ignore
    )
    ADMIN_ALERTS_AVAILABLE = True
except ImportError:
    ADMIN_ALERTS_AVAILABLE = False
    # Create robust fallback functions to prevent unbound errors
    async def send_critical_alert(component: str, message: str, category: str = "system_health", details: Optional[Dict[str, Any]] = None) -> bool:
        return False
    
    async def send_error_alert(component: str, message: str, category: str = "system_health", details: Optional[Dict[str, Any]] = None) -> bool:
        return False
    
    class AdminAlertCategory:
        PAYMENT_PROCESSING = 'payment_processing'

# Global flag for payment logging availability - always True since we handle fallbacks internally
PAYMENT_LOGGING_AVAILABLE = True

logger = logging.getLogger(__name__)

# Context variables for payment correlation tracking
_payment_correlation_id: ContextVar[Optional[str]] = ContextVar('payment_correlation_id', default=None)
_payment_trace_id: ContextVar[Optional[str]] = ContextVar('payment_trace_id', default=None)

# Payment logging configuration
class PaymentLogLevel(Enum):
    """Payment-specific log levels"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    AUDIT = "AUDIT"  # Special level for audit trail

class PaymentEventType(Enum):
    """Payment event types for categorization"""
    INTENT_CREATED = "intent_created"
    INTENT_UPDATED = "intent_updated"
    STATUS_TRANSITION = "status_transition"
    PROVIDER_API_CALL = "provider_api_call"
    PROVIDER_API_RESPONSE = "provider_api_response"
    WEBHOOK_RECEIVED = "webhook_received"
    WEBHOOK_PROCESSED = "webhook_processed"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PAYMENT_FAILED = "payment_failed"
    WALLET_CREDITED = "wallet_credited"
    CLEANUP_PERFORMED = "cleanup_performed"
    ERROR_OCCURRED = "error_occurred"
    PERFORMANCE_METRIC = "performance_metric"

class PaymentProvider(Enum):
    """Payment providers"""
    DYNOPAY = "dynopay"
    BLOCKBEE = "blockbee"
    STRIPE = "stripe"
    MANUAL = "manual"

@dataclass
class PaymentLogContext:
    """Structured payment logging context"""
    
    # Core identifiers
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None
    user_id: Optional[int] = None
    order_id: Optional[str] = None
    payment_intent_id: Optional[int] = None
    
    # Payment details
    provider: Optional[str] = None
    payment_method: Optional[str] = None
    currency: Optional[str] = None
    amount_usd: Optional[Union[float, Decimal]] = None
    amount_crypto: Optional[Union[float, Decimal]] = None
    
    # Status and transitions
    previous_status: Optional[str] = None
    current_status: Optional[str] = None
    
    # Provider-specific data
    external_payment_id: Optional[str] = None
    transaction_id: Optional[str] = None
    payment_address: Optional[str] = None
    confirmations: Optional[int] = None
    
    # Performance data
    operation_start_time: Optional[float] = None
    duration_ms: Optional[float] = None
    
    # Error context
    error_code: Optional[str] = None
    error_category: Optional[str] = None
    retry_count: Optional[int] = None
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, handling Decimal serialization"""
        result = {}
        for key, value in asdict(self).items():
            if isinstance(value, Decimal):
                result[key] = float(value)
            elif value is not None:
                result[key] = value
        return result

class PaymentLogger:
    """Centralized payment logging utility"""
    
    def __init__(self):
        self.component_name = "payment_system"
        self.logger = logging.getLogger("payment_system")
        
        # Setup structured logging format if not already configured
        self._setup_payment_logging()
        
        # Performance tracking
        self.operation_times = {}
        
        logger.info("✅ Payment logging system initialized")
    
    def _setup_payment_logging(self):
        """Setup payment-specific structured logging"""
        
        class PaymentStructuredFormatter(logging.Formatter):
            """Custom formatter for payment logs with JSON structure"""
            
            def format(self, record):
                from decimal import Decimal
                from enum import Enum
                
                def convert_decimals(obj):
                    """Recursively convert Decimal objects to float for JSON serialization"""
                    if isinstance(obj, Decimal):
                        return float(obj)
                    elif isinstance(obj, Enum):
                        return obj.value
                    elif isinstance(obj, dict):
                        return {k: convert_decimals(v) for k, v in obj.items()}
                    elif isinstance(obj, (list, tuple)):
                        return [convert_decimals(item) for item in obj]
                    return obj
                
                # Extract payment context
                payment_context = getattr(record, 'payment_context', {})
                correlation_id = getattr(record, 'correlation_id', None) or _payment_correlation_id.get()
                trace_id = getattr(record, 'trace_id', None) or _payment_trace_id.get()
                
                log_data = {
                    'timestamp': datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                    'level': record.levelname,
                    'component': getattr(record, 'component', 'payment_system'),
                    'event_type': getattr(record, 'event_type', None),
                    'message': record.getMessage(),
                    'correlation_id': correlation_id,
                    'trace_id': trace_id,
                    'user_id': getattr(record, 'user_id', None),
                    'order_id': getattr(record, 'order_id', None),
                    'payment_context': convert_decimals(payment_context)
                }
                
                # Remove None values for cleaner logs
                return json.dumps({k: v for k, v in log_data.items() if v is not None})
        
        # Only add handler if none exists
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(PaymentStructuredFormatter())
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def _get_correlation_context(self) -> Dict[str, Optional[str]]:
        """Get current correlation context"""
        return {
            'correlation_id': _payment_correlation_id.get(),
            'trace_id': _payment_trace_id.get()
        }
    
    def log_payment_event(
        self,
        event_type: PaymentEventType,
        message: str,
        context: Optional[PaymentLogContext] = None,
        level: PaymentLogLevel = PaymentLogLevel.INFO
    ):
        """Log a payment event with structured context"""
        
        # Ensure context exists
        if context is None:
            context = PaymentLogContext()
        
        # Set correlation IDs if not provided
        if not context.correlation_id:
            context.correlation_id = _payment_correlation_id.get()
        if not context.trace_id:
            context.trace_id = _payment_trace_id.get()
        
        # Log structured event
        log_level = getattr(logging, level.value)
        
        extra = {
            'component': self.component_name,
            'event_type': event_type.value,
            'correlation_id': context.correlation_id,
            'trace_id': context.trace_id,
            'user_id': context.user_id,
            'order_id': context.order_id,
            'payment_context': context.to_dict()
        }
        
        self.logger.log(log_level, message, extra=extra)
        
        # Also log to production logger if available
        if PRODUCTION_LOGGING_AVAILABLE:
            try:
                prod_logger = get_production_logger()
                if prod_logger:  # Additional safety check
                    prod_logger.log_structured(
                        getattr(ProdLogLevel, level.value),
                        self.component_name,
                        message,
                        context=context.to_dict(),
                        trace_id=context.trace_id,
                        user_id=context.user_id,
                        order_id=context.order_id
                    )
            except Exception as e:
                logger.debug(f"Production logging failed: {e}")
    
    def start_payment_operation(
        self,
        operation_name: str,
        context: Optional[PaymentLogContext] = None
    ) -> str:
        """Start tracking a payment operation for performance monitoring"""
        
        # Generate operation ID for tracking
        operation_id = f"{operation_name}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        
        # Record start time
        start_time = time.time()
        self.operation_times[operation_id] = start_time
        
        # Update context with timing
        if context:
            context.operation_start_time = start_time
        
        # Log operation start
        self.log_payment_event(
            PaymentEventType.PERFORMANCE_METRIC,
            f"Payment operation started: {operation_name}",
            context,
            PaymentLogLevel.DEBUG
        )
        
        return operation_id
    
    def end_payment_operation(
        self,
        operation_id: Optional[str],
        operation_name: str,
        success: bool = True,
        context: Optional[PaymentLogContext] = None,
        error: Optional[Exception] = None
    ):
        """End tracking a payment operation and log performance metrics"""
        
        # Calculate duration
        start_time = self.operation_times.pop(operation_id or '', time.time())
        duration_ms = (time.time() - start_time) * 1000
        
        # Update context with performance data
        if context:
            context.duration_ms = duration_ms
            if error:
                context.error_code = type(error).__name__
                context.error_category = "operation_failure"
        
        # Log performance metric
        self.log_payment_event(
            PaymentEventType.PERFORMANCE_METRIC,
            f"Payment operation completed: {operation_name} ({duration_ms:.2f}ms)",
            context,
            PaymentLogLevel.INFO if success else PaymentLogLevel.ERROR
        )
        
        # Record metric with production logger
        if PRODUCTION_LOGGING_AVAILABLE:
            try:
                log_performance_metric(
                    self.component_name,
                    operation_name,
                    duration_ms,
                    success
                )
            except Exception as e:
                logger.debug(f"Performance metric logging failed: {e}")
    
    def log_status_transition(
        self,
        previous_status: str,
        new_status: str,
        context: Optional[PaymentLogContext] = None,
        reason: Optional[str] = None
    ):
        """Log payment status transition for audit trail"""
        
        if context is None:
            context = PaymentLogContext()
        
        context.previous_status = previous_status
        context.current_status = new_status
        
        message = f"Payment status transition: {previous_status} → {new_status}"
        if reason:
            message += f" (reason: {reason})"
        
        self.log_payment_event(
            PaymentEventType.STATUS_TRANSITION,
            message,
            context,
            PaymentLogLevel.AUDIT
        )
    
    def log_provider_api_call(
        self,
        provider: str,
        endpoint: str,
        method: str,
        context: Optional[PaymentLogContext] = None,
        request_data: Optional[Dict] = None
    ):
        """Log payment provider API call"""
        
        if context is None:
            context = PaymentLogContext()
        
        context.provider = provider
        if request_data:
            # Sanitize sensitive data
            sanitized_data = self._sanitize_api_data(request_data)
            context.metadata['request_data'] = sanitized_data
        
        self.log_payment_event(
            PaymentEventType.PROVIDER_API_CALL,
            f"API call to {provider}: {method} {endpoint}",
            context,
            PaymentLogLevel.INFO
        )
    
    def log_provider_api_response(
        self,
        provider: str,
        endpoint: str,
        status_code: int,
        context: Optional[PaymentLogContext] = None,
        response_data: Optional[Dict] = None,
        duration_ms: Optional[float] = None
    ):
        """Log payment provider API response"""
        
        if context is None:
            context = PaymentLogContext()
        
        context.provider = provider
        context.duration_ms = duration_ms
        
        if response_data:
            # Sanitize sensitive data
            sanitized_data = self._sanitize_api_data(response_data)
            context.metadata['response_data'] = sanitized_data
            context.metadata['status_code'] = status_code
        
        level = PaymentLogLevel.INFO if 200 <= status_code < 300 else PaymentLogLevel.WARNING
        
        self.log_payment_event(
            PaymentEventType.PROVIDER_API_RESPONSE,
            f"API response from {provider}: {status_code} for {endpoint}",
            context,
            level
        )
    
    def log_webhook_processing(
        self,
        provider: str,
        webhook_data: Dict,
        processing_result: str,
        context: Optional[PaymentLogContext] = None,
        duration_ms: Optional[float] = None
    ):
        """Log webhook processing events"""
        
        if context is None:
            context = PaymentLogContext()
        
        context.provider = provider
        context.duration_ms = duration_ms
        
        # Extract key webhook data (sanitized)
        context.metadata['webhook_result'] = processing_result
        if 'order_id' in webhook_data:
            context.order_id = webhook_data['order_id']
        if 'status' in webhook_data:
            context.current_status = webhook_data['status']
        
        # Log webhook received
        self.log_payment_event(
            PaymentEventType.WEBHOOK_RECEIVED,
            f"Webhook received from {provider}",
            context,
            PaymentLogLevel.INFO
        )
        
        # Log processing result
        result_level = PaymentLogLevel.INFO if processing_result == "success" else PaymentLogLevel.ERROR
        self.log_payment_event(
            PaymentEventType.WEBHOOK_PROCESSED,
            f"Webhook processing {processing_result} from {provider}",
            context,
            result_level
        )
    
    def log_payment_error(
        self,
        error: Exception,
        context: Optional[PaymentLogContext] = None,
        error_category: str = "unknown",
        actionable_steps: Optional[List[str]] = None
    ):
        """Log payment error with enhanced context for troubleshooting"""
        
        if context is None:
            context = PaymentLogContext()
        
        context.error_code = type(error).__name__
        context.error_category = error_category
        
        # Add actionable troubleshooting steps
        error_context = {
            'error_message': str(error),
            'error_type': type(error).__name__,
            'category': error_category
        }
        
        if actionable_steps:
            error_context['actionable_steps'] = ', '.join(actionable_steps) if isinstance(actionable_steps, list) else str(actionable_steps)
        
        context.metadata.update(error_context)
        
        # Log structured error
        self.log_payment_event(
            PaymentEventType.ERROR_OCCURRED,
            f"Payment error ({error_category}): {error}",
            context,
            PaymentLogLevel.ERROR
        )
        
        # Log to production error system if available
        if PRODUCTION_LOGGING_AVAILABLE:
            try:
                log_error_with_context(
                    self.component_name,
                    error,
                    error_context,
                    context.user_id,
                    context.order_id
                )
            except Exception as e:
                logger.debug(f"Production error logging failed: {e}")
        
        # Send critical alert for severe errors
        if error_category in ['provider_api_failure', 'database_error', 'security_violation']:
            asyncio.create_task(self._send_critical_error_alert(error, context, error_category))
    
    async def _send_critical_error_alert(
        self,
        error: Exception,
        context: PaymentLogContext,
        error_category: str
    ):
        """Send critical error alert to administrators"""
        
        if not ADMIN_ALERTS_AVAILABLE:
            return
        
        try:
            await send_critical_alert(
                component="Payment System",
                message=f"Critical payment error: {error_category}",
                category=AdminAlertCategory.PAYMENT_PROCESSING.value if hasattr(AdminAlertCategory.PAYMENT_PROCESSING, 'value') else AdminAlertCategory.PAYMENT_PROCESSING,  # type: ignore
                details={
                    'error': str(error),
                    'error_type': type(error).__name__,
                    'category': error_category,
                    'order_id': context.order_id,
                    'user_id': context.user_id,
                    'provider': context.provider,
                    'correlation_id': context.correlation_id
                }
            )
        except Exception as alert_error:
            logger.error(f"❌ Failed to send critical payment error alert: {alert_error}")
    
    def _sanitize_api_data(self, data: Dict) -> Dict:
        """Sanitize API data by removing or masking sensitive information"""
        
        sensitive_fields = {
            'api_key', 'token', 'secret', 'password', 'private_key',
            'wallet_token', 'auth_token', 'authorization'
        }
        
        def sanitize_value(key: str, value: Any) -> Any:
            if isinstance(key, str) and key.lower() in sensitive_fields:
                if isinstance(value, str) and len(value) > 8:
                    return f"{value[:4]}...{value[-4:]}"
                else:
                    return "[REDACTED]"
            elif isinstance(value, dict):
                return {k: sanitize_value(k, v) for k, v in value.items()}
            elif isinstance(value, list):
                return [sanitize_value("", item) for item in value]
            else:
                return value
        
        return {k: sanitize_value(k, v) for k, v in data.items()}

# Context managers for payment operation tracking

class PaymentOperationContext:
    """Context manager for payment operation tracking"""
    
    def __init__(
        self,
        operation_name: str,
        logger: PaymentLogger,
        context: Optional[PaymentLogContext] = None
    ):
        self.operation_name = operation_name
        self.logger = logger
        self.context = context or PaymentLogContext()
        self.operation_id = None
        self.success = True
        self.error = None
    
    def __enter__(self):
        self.operation_id = self.logger.start_payment_operation(
            self.operation_name, self.context
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.success = False
            self.error = exc_val
        
        self.logger.end_payment_operation(
            self.operation_id,
            self.operation_name,
            self.success,
            self.context,
            self.error
        )
        
        return False  # Don't suppress exceptions

class PaymentCorrelationContext:
    """Context manager for payment correlation ID tracking"""
    
    def __init__(self, correlation_id: Optional[str] = None, trace_id: Optional[str] = None):
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.trace_id = trace_id or str(uuid.uuid4())
        self.correlation_token = None
        self.trace_token = None
    
    def __enter__(self):
        self.correlation_token = _payment_correlation_id.set(self.correlation_id)
        self.trace_token = _payment_trace_id.set(self.trace_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.correlation_token:
            _payment_correlation_id.reset(self.correlation_token)
        if self.trace_token:
            _payment_trace_id.reset(self.trace_token)

# Global payment logger instance
_payment_logger: Optional[PaymentLogger] = None

def get_payment_logger() -> PaymentLogger:
    """Get global payment logger instance"""
    global _payment_logger
    if _payment_logger is None:
        _payment_logger = PaymentLogger()
    return _payment_logger

# Convenience functions for common payment logging patterns

def log_payment_intent_created(
    order_id: str,
    user_id: int,
    amount_usd: Union[float, Decimal],
    provider: str,
    currency: str = "USD",
    correlation_id: Optional[str] = None
):
    """Log payment intent creation"""
    context = PaymentLogContext(
        correlation_id=correlation_id,
        user_id=user_id,
        order_id=order_id,
        provider=provider,
        currency=currency,
        amount_usd=amount_usd,
        current_status="created"
    )
    
    logger = get_payment_logger()
    logger.log_payment_event(
        PaymentEventType.INTENT_CREATED,
        f"Payment intent created for ${amount_usd} {currency}",
        context
    )

def log_payment_status_change(
    order_id: str,
    previous_status: str,
    new_status: str,
    user_id: Optional[int] = None,
    provider: Optional[str] = None,
    reason: Optional[str] = None,
    correlation_id: Optional[str] = None
):
    """Log payment status transition"""
    context = PaymentLogContext(
        correlation_id=correlation_id,
        user_id=user_id,
        order_id=order_id,
        provider=provider,
        previous_status=previous_status,
        current_status=new_status
    )
    
    logger = get_payment_logger()
    logger.log_status_transition(previous_status, new_status, context, reason)

def log_payment_provider_call(
    provider: str,
    endpoint: str,
    method: str,
    order_id: Optional[str] = None,
    user_id: Optional[int] = None,
    correlation_id: Optional[str] = None
):
    """Log payment provider API call"""
    context = PaymentLogContext(
        correlation_id=correlation_id,
        user_id=user_id,
        order_id=order_id
    )
    
    logger = get_payment_logger()
    logger.log_provider_api_call(provider, endpoint, method, context)

def log_payment_confirmed(
    order_id: str,
    user_id: int,
    amount_usd: Union[float, Decimal],
    provider: str,
    transaction_id: str,
    correlation_id: Optional[str] = None
):
    """Log successful payment confirmation"""
    context = PaymentLogContext(
        correlation_id=correlation_id,
        user_id=user_id,
        order_id=order_id,
        provider=provider,
        amount_usd=amount_usd,
        transaction_id=transaction_id,
        current_status="confirmed"
    )
    
    logger = get_payment_logger()
    logger.log_payment_event(
        PaymentEventType.PAYMENT_CONFIRMED,
        f"Payment confirmed: ${amount_usd} via {provider}",
        context
    )

def log_wallet_credited(
    user_id: int,
    amount_usd: Union[float, Decimal],
    transaction_id: str,
    source_order_id: Optional[str] = None,
    correlation_id: Optional[str] = None
):
    """Log wallet credit operation"""
    context = PaymentLogContext(
        correlation_id=correlation_id,
        user_id=user_id,
        order_id=source_order_id,
        amount_usd=amount_usd,
        transaction_id=transaction_id,
        current_status="completed"
    )
    
    logger = get_payment_logger()
    logger.log_payment_event(
        PaymentEventType.WALLET_CREDITED,
        f"Wallet credited with ${amount_usd}",
        context
    )

# Decorators for automatic payment operation tracking

def track_payment_operation(operation_name: str):
    """Decorator to automatically track payment operation performance"""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            logger = get_payment_logger()
            with PaymentOperationContext(operation_name, logger):
                return await func(*args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            logger = get_payment_logger()
            with PaymentOperationContext(operation_name, logger):
                return func(*args, **kwargs)
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator

# Export main interfaces
__all__ = [
    'PaymentLogger',
    'PaymentLogContext', 
    'PaymentEventType',
    'PaymentLogLevel',
    'PaymentOperationContext',
    'PaymentCorrelationContext',
    'get_payment_logger',
    'log_payment_intent_created',
    'log_payment_status_change',
    'log_payment_provider_call',
    'log_payment_confirmed',
    'log_wallet_credited',
    'track_payment_operation'
]