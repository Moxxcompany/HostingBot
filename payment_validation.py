"""
Unified payment validation module for consistent tolerance handling
Shared by both webhook handler and database operations to ensure consistent behavior
"""

import os
import asyncio
import logging
from typing import Dict, Optional, Union
from decimal import Decimal

logger = logging.getLogger(__name__)

def get_payment_tolerance_config():
    """Get payment validation tolerance configuration from environment variables"""
    return {
        'underpayment_tolerance_percent': float(os.getenv('PAYMENT_UNDERPAYMENT_TOLERANCE_PERCENT', '3.0')),  # 3% default
        'max_underpayment_tolerance_percent': float(os.getenv('PAYMENT_MAX_UNDERPAYMENT_TOLERANCE_PERCENT', '5.0')),  # 5% maximum
        'overpayment_limit_percent': float(os.getenv('PAYMENT_OVERPAYMENT_LIMIT_PERCENT', '0')),  # 0 = unlimited
        'minimum_underpayment_tolerance_usd': float(os.getenv('PAYMENT_MIN_UNDERPAYMENT_TOLERANCE_USD', '0.10')),  # $0.10 minimum tolerance
        'strict_validation_enabled': os.getenv('PAYMENT_STRICT_VALIDATION', 'false').lower() == 'true'
    }

class PaymentValidationResult:
    """Result object for payment validation with detailed information"""
    def __init__(self, is_valid: bool, reason: str, details: dict):
        self.is_valid = is_valid
        self.reason = reason
        self.details = details
        # Keep as Decimal for financial precision
        tolerance_used = details.get('tolerance_used_percent', 0)
        self.tolerance_used = tolerance_used if isinstance(tolerance_used, Decimal) else Decimal(str(tolerance_used))
        amount_diff = details.get('amount_difference_usd', 0)
        self.amount_difference = amount_diff if isinstance(amount_diff, Decimal) else Decimal(str(amount_diff))
        self.validation_type = details.get('validation_type', 'unknown')

def validate_payment_amount(expected_usd: Union[Decimal, float], received_usd: Union[Decimal, float], crypto_currency: str = 'crypto', received_crypto: Union[Decimal, float] = 0.0, payment_type: str = 'general', caller: str = 'unknown') -> PaymentValidationResult:
    """
    Unified payment validation with configurable tolerance for cryptocurrency volatility and fees
    Used by both webhook handler and database operations to ensure consistent behavior
    
    Args:
        expected_usd: Expected payment amount in USD (Decimal or float)
        received_usd: Received payment amount in USD (Decimal or float, converted from crypto)
        crypto_currency: Cryptocurrency used for payment
        received_crypto: Amount received in cryptocurrency
        payment_type: Type of payment ('wallet_deposit', 'domain_order', etc.)
        caller: Component calling validation ('webhook', 'database', etc.) for logging
        
    Returns:
        PaymentValidationResult: Detailed validation result with decision reasoning
    """
    config = get_payment_tolerance_config()
    
    # Convert to Decimal for precise financial calculations
    expected_decimal = Decimal(str(expected_usd)) if not isinstance(expected_usd, Decimal) else expected_usd
    received_decimal = Decimal(str(received_usd)) if not isinstance(received_usd, Decimal) else received_usd
    received_crypto_decimal = Decimal(str(received_crypto)) if not isinstance(received_crypto, Decimal) else received_crypto
    
    # Calculate amount difference using Decimal arithmetic
    amount_difference_usd = received_decimal - expected_decimal
    amount_difference_percent = (amount_difference_usd / expected_decimal * 100) if expected_decimal > 0 else Decimal('0')
    
    # Log validation attempt with full context including caller
    logger.info(f"💰 UNIFIED VALIDATION: {payment_type} (called from {caller})")
    logger.info(f"   Expected: ${expected_decimal:.4f} USD")
    logger.info(f"   Received: ${received_decimal:.4f} USD ({received_crypto_decimal:.8f} {crypto_currency})")
    logger.info(f"   Difference: ${amount_difference_usd:.4f} USD ({amount_difference_percent:+.2f}%)")
    logger.info(f"   Tolerance Config: {config['underpayment_tolerance_percent']:.1f}% underpayment, {config['overpayment_limit_percent']:.1f}% overpayment limit")
    
    # Validation details to return (keep ALL financial values as Decimal for precision)
    # DO NOT include tolerance_config here as it contains floats - only store Decimal tolerance values
    validation_details = {
        'expected_usd': expected_decimal,
        'received_usd': received_decimal,
        'amount_difference_usd': amount_difference_usd,  # Decimal
        'amount_difference_percent': amount_difference_percent,  # Decimal
        'crypto_currency': crypto_currency,
        'received_crypto': received_crypto_decimal,  # Decimal
        'caller': caller,
        'payment_type': payment_type,
        'validation_timestamp': asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0
    }
    
    # CASE 1: Exact or overpayment
    if amount_difference_usd >= 0:
        # Check overpayment limits (if configured) - convert to Decimal for comparison
        overpayment_limit = Decimal(str(config['overpayment_limit_percent']))
        if overpayment_limit > 0 and amount_difference_percent > overpayment_limit:
            validation_details['validation_type'] = 'overpayment_exceeded'
            validation_details['overpayment_limit_exceeded'] = True
            logger.warning(f"🚫 UNIFIED VALIDATION REJECTED: Overpayment exceeds limit ({amount_difference_percent:.2f}% > {config['overpayment_limit_percent']:.1f}%)")
            return PaymentValidationResult(
                is_valid=False,
                reason=f"Overpayment exceeds configured limit of {config['overpayment_limit_percent']:.1f}% (received {amount_difference_percent:+.2f}%)",
                details=validation_details
            )
        
        # Overpayment accepted
        validation_details['validation_type'] = 'overpayment_accepted' if amount_difference_usd > 0 else 'exact_payment'
        logger.info(f"✅ UNIFIED VALIDATION ACCEPTED: {'Overpayment' if amount_difference_usd > 0 else 'Exact payment'} ({amount_difference_percent:+.2f}%)")
        return PaymentValidationResult(
            is_valid=True,
            reason=f"Payment accepted - {'overpayment' if amount_difference_usd > 0 else 'exact amount'} received",
            details=validation_details
        )
    
    # CASE 2: Underpayment - Apply tolerance rules
    underpayment_amount = abs(amount_difference_usd)
    underpayment_percent = abs(amount_difference_percent)
    
    # Check if strict validation is enabled (no tolerance)
    if config['strict_validation_enabled']:
        validation_details['validation_type'] = 'strict_validation_failed'
        logger.warning(f"🚫 UNIFIED VALIDATION REJECTED: Strict validation enabled - no underpayment tolerance (${underpayment_amount:.4f} short)")
        return PaymentValidationResult(
            is_valid=False,
            reason=f"Strict validation: Underpayment not allowed (${underpayment_amount:.4f} short, {underpayment_percent:.2f}% under)",
            details=validation_details
        )
    
    # Calculate effective tolerance (considering minimums and maximums)
    effective_tolerance_percent = Decimal(str(min(
        config['underpayment_tolerance_percent'],
        config['max_underpayment_tolerance_percent']
    )))
    
    # Ensure minimum tolerance in USD terms for very small payments
    minimum_tolerance_usd = Decimal(str(config['minimum_underpayment_tolerance_usd']))
    tolerance_usd = max(
        expected_decimal * (effective_tolerance_percent / 100),
        minimum_tolerance_usd
    )
    
    validation_details['tolerance_used_percent'] = effective_tolerance_percent  # Keep as Decimal
    validation_details['tolerance_used_usd'] = tolerance_usd  # Keep as Decimal
    validation_details['minimum_tolerance_applied'] = (tolerance_usd == minimum_tolerance_usd)
    
    # Apply tolerance validation
    if underpayment_amount <= tolerance_usd:
        validation_details['validation_type'] = 'underpayment_within_tolerance'
        logger.info(f"✅ UNIFIED VALIDATION ACCEPTED: Underpayment within tolerance")
        logger.info(f"   Underpayment: ${underpayment_amount:.4f} USD ({underpayment_percent:.2f}%)")
        logger.info(f"   Tolerance: ${tolerance_usd:.4f} USD ({effective_tolerance_percent:.2f}%)")
        logger.info(f"   Reason: {'Crypto volatility/fees accommodation' if not validation_details['minimum_tolerance_applied'] else 'Minimum tolerance applied'}")
        
        return PaymentValidationResult(
            is_valid=True,
            reason=f"Underpayment within tolerance (${underpayment_amount:.4f} under, tolerance: ${tolerance_usd:.4f})",
            details=validation_details
        )
    else:
        validation_details['validation_type'] = 'underpayment_exceeds_tolerance'
        logger.warning(f"🚫 UNIFIED VALIDATION REJECTED: Underpayment exceeds tolerance")
        logger.warning(f"   Underpayment: ${underpayment_amount:.4f} USD ({underpayment_percent:.2f}%)")
        logger.warning(f"   Tolerance: ${tolerance_usd:.4f} USD ({effective_tolerance_percent:.2f}%)")
        logger.warning(f"   Shortage: ${underpayment_amount - tolerance_usd:.4f} USD beyond tolerance")
        
        return PaymentValidationResult(
            is_valid=False,
            reason=f"Underpayment exceeds tolerance (${underpayment_amount:.4f} short, tolerance: ${tolerance_usd:.4f})",
            details=validation_details
        )

def validate_payment_simple(expected_usd: Union[Decimal, float], received_usd: Union[Decimal, float], payment_type: str = 'general', caller: str = 'unknown') -> bool:
    """
    Synchronous payment validation function for thread-safe database operations
    Returns True if payment is valid, False otherwise
    
    This is a synchronous implementation that duplicates the logic from validate_payment_amount
    to avoid async context issues when called from asyncio.to_thread() contexts.
    Uses Decimal arithmetic for financial precision.
    """
    config = get_payment_tolerance_config()
    
    # Convert to Decimal for precise financial calculations
    expected_decimal = Decimal(str(expected_usd)) if not isinstance(expected_usd, Decimal) else expected_usd
    received_decimal = Decimal(str(received_usd)) if not isinstance(received_usd, Decimal) else received_usd
    
    # Calculate amount difference using Decimal arithmetic
    amount_difference_usd = received_decimal - expected_decimal
    amount_difference_percent = (amount_difference_usd / expected_decimal * 100) if expected_decimal > 0 else Decimal('0')
    
    # Log validation attempt with full context
    logger.info(f"🔒 SYNC VALIDATION ({caller.upper()}): {payment_type}")
    logger.info(f"   Expected: ${expected_decimal:.4f} USD")
    logger.info(f"   Received: ${received_decimal:.4f} USD")
    logger.info(f"   Difference: ${amount_difference_usd:.4f} USD ({amount_difference_percent:+.2f}%)")
    
    # Perfect match - always valid (using Decimal comparison)
    if abs(amount_difference_usd) < Decimal('0.0001'):  # Within 0.01 cent
        logger.info("✅ SYNC VALIDATION: Perfect payment amount match")
        return True
    
    # Overpayment handling
    if amount_difference_usd > 0:
        overpayment_percent = amount_difference_percent
        
        # Check overpayment limits if configured - convert to Decimal for comparison
        overpayment_limit = Decimal(str(config['overpayment_limit_percent']))
        if overpayment_limit > 0 and overpayment_percent > overpayment_limit:
            logger.warning(f"🚫 SYNC VALIDATION REJECTED: Overpayment exceeds limit")
            logger.warning(f"   Overpayment: ${amount_difference_usd:.4f} USD ({overpayment_percent:.2f}%)")
            logger.warning(f"   Limit: {config['overpayment_limit_percent']:.1f}%")
            return False
        else:
            logger.info(f"✅ SYNC VALIDATION ACCEPTED: Overpayment within limits")
            logger.info(f"   Overpayment: ${amount_difference_usd:.4f} USD ({overpayment_percent:.2f}%)")
            return True
    
    # Underpayment handling with tolerance (using Decimal arithmetic)
    underpayment_amount = abs(amount_difference_usd)
    underpayment_percent = abs(amount_difference_percent)
    
    # Calculate tolerance with Decimal precision
    tolerance_percent = Decimal(str(min(config['underpayment_tolerance_percent'], config['max_underpayment_tolerance_percent'])))
    tolerance_usd = (expected_decimal * tolerance_percent / 100)
    minimum_tolerance_usd = Decimal(str(config['minimum_underpayment_tolerance_usd']))
    
    # Apply minimum tolerance
    effective_tolerance_percent = tolerance_percent
    if tolerance_usd < minimum_tolerance_usd:
        tolerance_usd = minimum_tolerance_usd
        effective_tolerance_percent = (minimum_tolerance_usd / expected_decimal * 100) if expected_decimal > 0 else Decimal('0')
    
    # Apply tolerance validation
    if underpayment_amount <= tolerance_usd:
        logger.info(f"✅ SYNC VALIDATION ACCEPTED: Underpayment within tolerance")
        logger.info(f"   Underpayment: ${underpayment_amount:.4f} USD ({underpayment_percent:.2f}%)")
        logger.info(f"   Tolerance: ${tolerance_usd:.4f} USD ({effective_tolerance_percent:.2f}%)")
        return True
    else:
        logger.warning(f"🚫 SYNC VALIDATION REJECTED: Underpayment exceeds tolerance")
        logger.warning(f"   Underpayment: ${underpayment_amount:.4f} USD ({underpayment_percent:.2f}%)")
        logger.warning(f"   Tolerance: ${tolerance_usd:.4f} USD ({effective_tolerance_percent:.2f}%)")
        logger.warning(f"   Shortage: ${underpayment_amount - tolerance_usd:.4f} USD beyond tolerance")
        return False

def log_validation_config(caller: str = 'unknown'):
    """Log current validation configuration for debugging"""
    config = get_payment_tolerance_config()
    logger.info(f"🔧 VALIDATION CONFIG ({caller}):")
    logger.info(f"   • Underpayment tolerance: {config['underpayment_tolerance_percent']:.1f}%")
    logger.info(f"   • Max underpayment tolerance: {config['max_underpayment_tolerance_percent']:.1f}%")
    logger.info(f"   • Overpayment limit: {config['overpayment_limit_percent']:.1f}% ({'unlimited' if config['overpayment_limit_percent'] == 0 else 'limited'})")
    logger.info(f"   • Minimum tolerance USD: ${config['minimum_underpayment_tolerance_usd']:.2f}")
    logger.info(f"   • Strict validation: {'ENABLED' if config['strict_validation_enabled'] else 'DISABLED'}")