#!/usr/bin/env python3
"""
Type-Safe Converter System for HostBay
Eliminates conversion errors by providing safe, validated type conversions
Prevents "could not convert string to float: 'cxh5tph6f3.de'" style errors
"""

import logging
import re
import uuid as uuid_lib
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Union, Any, List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

# Validation patterns
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
DOMAIN_PATTERN = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$')
CURRENCY_CODE_PATTERN = re.compile(r'^[A-Z]{3}$')
UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', re.IGNORECASE)

# Common currency codes that should never be in amount fields
KNOWN_CURRENCY_CODES = {'USD', 'EUR', 'GBP', 'BTC', 'ETH', 'LTC', 'DOGE', 'USDT', 'USDC', 'DAI'}

def safe_decimal(
    value: Any,
    default: Optional[Decimal] = None,
    field_name: str = "amount",
    min_value: Optional[Decimal] = None,
    max_value: Optional[Decimal] = None,
    decimal_places: int = 2
) -> Optional[Decimal]:
    """
    Safely convert any value to Decimal with comprehensive validation
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        field_name: Field name for logging
        min_value: Minimum allowed value
        max_value: Maximum allowed value  
        decimal_places: Decimal places to round to
        
    Returns:
        Decimal value or default
        
    Prevents common errors:
        - Domain names in amount fields: 'cxh5tph6f3.de' 
        - Currency codes in amount fields: 'USD'
        - Invalid strings, None values, etc.
    """
    if value is None:
        logger.debug(f"🔍 SAFE_DECIMAL: {field_name} is None, using default: {default}")
        return default
    
    # Handle already-Decimal values
    if isinstance(value, Decimal):
        result = value.quantize(Decimal('0.' + '0' * decimal_places), rounding=ROUND_HALF_UP)
        return _validate_decimal_bounds(result, field_name, min_value, max_value, default)
    
    # Handle numeric types
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (value != value):  # NaN check
            logger.error(f"❌ SAFE_DECIMAL: {field_name} contains NaN value")
            return default
        
        try:
            result = Decimal(str(value)).quantize(Decimal('0.' + '0' * decimal_places), rounding=ROUND_HALF_UP)
            return _validate_decimal_bounds(result, field_name, min_value, max_value, default)
        except (InvalidOperation, ValueError) as e:
            logger.error(f"❌ SAFE_DECIMAL: Failed to convert numeric {field_name}={value} (type: {type(value).__name__}): {e}")
            return default
    
    # Handle string values with comprehensive validation
    if isinstance(value, str):
        value_stripped = value.strip()
        
        # Empty string check
        if not value_stripped:
            logger.debug(f"🔍 SAFE_DECIMAL: {field_name} is empty string, using default: {default}")
            return default
        
        # CRITICAL: Check for domain names (contains dots and letters)
        if '.' in value_stripped and any(c.isalpha() for c in value_stripped):
            # Additional check: does it look like a domain?
            if DOMAIN_PATTERN.match(value_stripped.lower()) or '/' in value_stripped:
                logger.error(f"❌ SAFE_DECIMAL: {field_name} contains domain name: '{value_stripped}' - REJECTED")
                return default
        
        # Check for currency codes
        if value_stripped.upper() in KNOWN_CURRENCY_CODES:
            logger.error(f"❌ SAFE_DECIMAL: {field_name} contains currency code: '{value_stripped}' - REJECTED")
            return default
        
        # Check if it looks like an email
        if '@' in value_stripped and EMAIL_PATTERN.match(value_stripped):
            logger.error(f"❌ SAFE_DECIMAL: {field_name} contains email address: '{value_stripped}' - REJECTED")
            return default
        
        # Try to convert to decimal
        try:
            # Remove common non-numeric characters that might be in amounts
            clean_value = value_stripped.replace(',', '').replace('$', '').replace('€', '').replace('£', '')
            result = Decimal(clean_value).quantize(Decimal('0.' + '0' * decimal_places), rounding=ROUND_HALF_UP)
            return _validate_decimal_bounds(result, field_name, min_value, max_value, default)
        except (InvalidOperation, ValueError) as e:
            logger.error(f"❌ SAFE_DECIMAL: Failed to convert string {field_name}='{value_stripped}' to decimal: {e}")
            return default
    
    # Handle other types
    logger.error(f"❌ SAFE_DECIMAL: Unsupported type for {field_name}: {type(value).__name__} = {value}")
    return default

def _validate_decimal_bounds(
    value: Decimal, 
    field_name: str, 
    min_value: Optional[Decimal], 
    max_value: Optional[Decimal], 
    default: Optional[Decimal]
) -> Optional[Decimal]:
    """Validate decimal value against bounds"""
    if min_value is not None and value < min_value:
        logger.error(f"❌ SAFE_DECIMAL: {field_name}={value} is below minimum {min_value}")
        return default
        
    if max_value is not None and value > max_value:
        logger.error(f"❌ SAFE_DECIMAL: {field_name}={value} is above maximum {max_value}")
        return default
        
    return value

def safe_int(
    value: Any,
    default: Optional[int] = None,
    field_name: str = "number",
    min_value: Optional[int] = None,
    max_value: Optional[int] = None
) -> Optional[int]:
    """
    Safely convert any value to integer
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        field_name: Field name for logging
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        
    Returns:
        Integer value or default
    """
    if value is None:
        logger.debug(f"🔍 SAFE_INT: {field_name} is None, using default: {default}")
        return default
    
    # Handle already-int values
    if isinstance(value, int):
        return _validate_int_bounds(value, field_name, min_value, max_value, default)
    
    # Handle float values (convert to int)
    if isinstance(value, float):
        if value != value:  # NaN check
            logger.error(f"❌ SAFE_INT: {field_name} contains NaN value")
            return default
        try:
            result = int(value)
            return _validate_int_bounds(result, field_name, min_value, max_value, default)
        except (ValueError, OverflowError) as e:
            logger.error(f"❌ SAFE_INT: Failed to convert float {field_name}={value}: {e}")
            return default
    
    # Handle Decimal values
    if isinstance(value, Decimal):
        try:
            result = int(value)
            return _validate_int_bounds(result, field_name, min_value, max_value, default)
        except (ValueError, InvalidOperation) as e:
            logger.error(f"❌ SAFE_INT: Failed to convert Decimal {field_name}={value}: {e}")
            return default
    
    # Handle string values
    if isinstance(value, str):
        value_stripped = value.strip()
        
        if not value_stripped:
            logger.debug(f"🔍 SAFE_INT: {field_name} is empty string, using default: {default}")
            return default
        
        # Check for domain names or other invalid patterns
        if '.' in value_stripped and any(c.isalpha() for c in value_stripped):
            logger.error(f"❌ SAFE_INT: {field_name} contains invalid string: '{value_stripped}' - REJECTED")
            return default
        
        try:
            result = int(float(value_stripped))  # Handle strings like "123.0"
            return _validate_int_bounds(result, field_name, min_value, max_value, default)
        except (ValueError, OverflowError) as e:
            logger.error(f"❌ SAFE_INT: Failed to convert string {field_name}='{value_stripped}' to int: {e}")
            return default
    
    logger.error(f"❌ SAFE_INT: Unsupported type for {field_name}: {type(value).__name__} = {value}")
    return default

def _validate_int_bounds(
    value: int, 
    field_name: str, 
    min_value: Optional[int], 
    max_value: Optional[int], 
    default: Optional[int]
) -> Optional[int]:
    """Validate integer value against bounds"""
    if min_value is not None and value < min_value:
        logger.error(f"❌ SAFE_INT: {field_name}={value} is below minimum {min_value}")
        return default
        
    if max_value is not None and value > max_value:
        logger.error(f"❌ SAFE_INT: {field_name}={value} is above maximum {max_value}")
        return default
        
    return value

def safe_uuid(
    value: Any,
    default: Optional[str] = None,
    field_name: str = "uuid",
    allow_none: bool = True
) -> Optional[str]:
    """
    Safely convert any value to UUID string
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        field_name: Field name for logging
        allow_none: Whether None values are acceptable
        
    Returns:
        UUID string or default
    """
    if value is None:
        if allow_none:
            logger.debug(f"🔍 SAFE_UUID: {field_name} is None, using default: {default}")
            return default
        else:
            logger.error(f"❌ SAFE_UUID: {field_name} is None but not allowed")
            return default
    
    # Handle UUID objects
    if isinstance(value, uuid_lib.UUID):
        return str(value)
    
    # Handle string values
    if isinstance(value, str):
        value_stripped = value.strip()
        
        if not value_stripped:
            logger.debug(f"🔍 SAFE_UUID: {field_name} is empty string, using default: {default}")
            return default
        
        # Validate UUID format
        if UUID_PATTERN.match(value_stripped):
            try:
                # Validate by parsing
                uuid_obj = uuid_lib.UUID(value_stripped)
                return str(uuid_obj)
            except ValueError as e:
                logger.error(f"❌ SAFE_UUID: Invalid UUID format {field_name}='{value_stripped}': {e}")
                return default
        else:
            logger.error(f"❌ SAFE_UUID: Invalid UUID pattern {field_name}='{value_stripped}'")
            return default
    
    logger.error(f"❌ SAFE_UUID: Unsupported type for {field_name}: {type(value).__name__} = {value}")
    return default

def safe_string(
    value: Any,
    default: Optional[str] = None,
    field_name: str = "string",
    max_length: Optional[int] = None,
    strip_whitespace: bool = True,
    allow_empty: bool = True
) -> Optional[str]:
    """
    Safely convert any value to string with validation
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        field_name: Field name for logging
        max_length: Maximum allowed length
        strip_whitespace: Whether to strip whitespace
        allow_empty: Whether empty strings are acceptable
        
    Returns:
        String value or default
    """
    if value is None:
        logger.debug(f"🔍 SAFE_STRING: {field_name} is None, using default: {default}")
        return default
    
    # Handle string values
    if isinstance(value, str):
        result = value.strip() if strip_whitespace else value
        
        if not allow_empty and not result:
            logger.debug(f"🔍 SAFE_STRING: {field_name} is empty string and not allowed, using default: {default}")
            return default
        
        if max_length is not None and len(result) > max_length:
            logger.warning(f"⚠️ SAFE_STRING: {field_name} length {len(result)} exceeds maximum {max_length}, truncating")
            result = result[:max_length]
        
        return result
    
    # Handle other types by converting to string
    try:
        result = str(value)
        if strip_whitespace:
            result = result.strip()
        
        if not allow_empty and not result:
            logger.debug(f"🔍 SAFE_STRING: {field_name} converted to empty string and not allowed, using default: {default}")
            return default
        
        if max_length is not None and len(result) > max_length:
            logger.warning(f"⚠️ SAFE_STRING: {field_name} length {len(result)} exceeds maximum {max_length}, truncating")
            result = result[:max_length]
        
        return result
    except Exception as e:
        logger.error(f"❌ SAFE_STRING: Failed to convert {field_name} (type: {type(value).__name__}): {e}")
        return default

def validate_email(email: str) -> bool:
    """Validate email address format"""
    if not isinstance(email, str):
        return False
    return bool(EMAIL_PATTERN.match(email.strip()))

def validate_domain(domain: str) -> bool:
    """Validate domain name format"""
    if not isinstance(domain, str):
        return False
    return bool(DOMAIN_PATTERN.match(domain.strip().lower()))

def validate_currency_code(code: str) -> bool:
    """Validate 3-letter currency code format"""
    if not isinstance(code, str):
        return False
    return bool(CURRENCY_CODE_PATTERN.match(code.strip().upper()))

def is_likely_domain_name(value: Any) -> bool:
    """
    Check if a value looks like a domain name
    Used to prevent domain names from being used in amount fields
    """
    if not isinstance(value, str):
        return False
    
    value_clean = value.strip().lower()
    
    # CRITICAL FIX: Domain names must contain at least one letter
    # Pure numeric values like "39.63" or "192.168.1.1" are NOT domain names
    if not any(c.isalpha() for c in value_clean):
        return False
    
    # Basic domain pattern check
    if DOMAIN_PATTERN.match(value_clean):
        return True
    
    # Additional heuristics for domain-like strings
    if ('.' in value_clean and 
        any(c.isalpha() for c in value_clean) and
        len(value_clean.split('.')) >= 2):
        return True
    
    return False

def safe_currency_conversion(
    amount: Any,
    from_currency: str,
    to_currency: str,
    exchange_rate: Any,
    field_name: str = "converted_amount"
) -> Optional[Decimal]:
    """
    Safely convert currency amounts using exchange rates
    
    Args:
        amount: Amount to convert
        from_currency: Source currency code
        to_currency: Target currency code  
        exchange_rate: Exchange rate from source to target
        field_name: Field name for logging
        
    Returns:
        Converted amount as Decimal or None
    """
    # Convert amount to Decimal safely
    decimal_amount = safe_decimal(amount, field_name=f"{field_name}_amount")
    if decimal_amount is None:
        return None
    
    # Convert exchange rate to Decimal safely  
    decimal_rate = safe_decimal(exchange_rate, field_name=f"{field_name}_rate")
    if decimal_rate is None:
        return None
    
    # Validate currencies
    if not (validate_currency_code(from_currency) and validate_currency_code(to_currency)):
        logger.error(f"❌ CURRENCY_CONVERSION: Invalid currency codes: {from_currency} -> {to_currency}")
        return None
    
    # Perform conversion
    try:
        result = decimal_amount * decimal_rate
        result = result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)  # Round to cents
        
        logger.debug(f"💱 CURRENCY_CONVERSION: {decimal_amount} {from_currency} -> {result} {to_currency} (rate: {decimal_rate})")
        return result
    except (InvalidOperation, ValueError) as e:
        logger.error(f"❌ CURRENCY_CONVERSION: Failed to convert {decimal_amount} {from_currency} to {to_currency}: {e}")
        return None

# Convenience functions for common use cases
def safe_amount(value: Any, field_name: str = "amount") -> Optional[Decimal]:
    """Safe conversion for monetary amounts with standard bounds"""
    return safe_decimal(
        value,
        default=None,
        field_name=field_name,
        min_value=Decimal('0'),
        max_value=Decimal('999999.99'),
        decimal_places=2
    )

def safe_crypto_amount(value: Any, field_name: str = "crypto_amount") -> Optional[Decimal]:
    """Safe conversion for cryptocurrency amounts with high precision"""
    return safe_decimal(
        value,
        default=None,
        field_name=field_name,
        min_value=Decimal('0'),
        max_value=Decimal('999999999.99999999'),
        decimal_places=8
    )

def safe_percentage(value: Any, field_name: str = "percentage") -> Optional[Decimal]:
    """Safe conversion for percentage values (0-100)"""
    return safe_decimal(
        value,
        default=None,
        field_name=field_name,
        min_value=Decimal('0'),
        max_value=Decimal('100'),
        decimal_places=2
    )

# Test data for validation
TEST_CASES = [
    # Valid amounts
    ("10.50", Decimal('10.50')),
    (10.5, Decimal('10.50')), 
    (Decimal('10.50'), Decimal('10.50')),
    ("0", Decimal('0.00')),
    
    # Invalid amounts (should return None)
    ("cxh5tph6f3.de", None),  # The specific error case
    ("example.com", None),
    ("user@example.com", None), 
    ("USD", None),
    ("BTC", None),
    ("", None),
    (None, None),
    ("not_a_number", None),
]

def run_test_cases():
    """Run test cases to verify the converter works correctly"""
    logger.info("🧪 Running type converter test cases...")
    
    for test_input, expected in TEST_CASES:
        result = safe_amount(test_input, "test_amount")
        status = "✅ PASS" if result == expected else "❌ FAIL"
        logger.info(f"{status}: safe_amount('{test_input}') = {result} (expected: {expected})")
    
    logger.info("🧪 Test cases completed")

if __name__ == "__main__":
    # Run tests when executed directly
    logging.basicConfig(level=logging.INFO)
    run_test_cases()