"""
Global Financial Precision Configuration for HostBay
Ensures consistent Decimal precision for all monetary calculations
"""

from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Union, Optional
import logging

logger = logging.getLogger(__name__)

# Set global precision context for financial calculations
getcontext().prec = 28  # High precision for financial calculations
getcontext().rounding = ROUND_HALF_UP  # Standard banking rounding

# Constants for common monetary operations
ZERO = Decimal('0')
ONE = Decimal('1')
CENT = Decimal('0.01')
HUNDRED = Decimal('100')

def to_decimal(value: Union[str, int, float, Decimal, None], field_name: str = "amount") -> Decimal:
    """
    Safely convert any numeric value to Decimal with high precision
    
    Args:
        value: The value to convert
        field_name: Name of the field for error reporting
        
    Returns:
        Decimal value with proper precision
        
    Raises:
        ValueError: If value cannot be converted to Decimal
    """
    if value is None:
        return ZERO
    
    if isinstance(value, Decimal):
        return value
    
    if isinstance(value, (int, float)):
        # Convert to string first to avoid float precision issues
        return Decimal(str(value))
    
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except Exception as e:
            raise ValueError(f"Invalid {field_name} format: '{value}' - {e}")
    
    # Try to convert other types
    try:
        return Decimal(str(value))
    except Exception as e:
        raise ValueError(f"Cannot convert {field_name} value {value} (type: {type(value)}) to Decimal: {e}")

def to_currency_decimal(value: Union[str, int, float, Decimal, None], field_name: str = "amount") -> Decimal:
    """
    Convert value to Decimal and round to 2 decimal places for currency
    
    Args:
        value: The value to convert
        field_name: Name of the field for error reporting
        
    Returns:
        Decimal value rounded to 2 decimal places
    """
    decimal_value = to_decimal(value, field_name)
    return decimal_value.quantize(CENT, rounding=ROUND_HALF_UP)

def to_percentage_decimal(value: Union[str, int, float, Decimal, None], field_name: str = "percentage") -> Decimal:
    """
    Convert value to Decimal percentage (e.g., 5.5 for 5.5%)
    
    Args:
        value: The percentage value to convert
        field_name: Name of the field for error reporting
        
    Returns:
        Decimal percentage value
    """
    return to_decimal(value, field_name)

def decimal_multiply(a: Union[str, int, float, Decimal], b: Union[str, int, float, Decimal]) -> Decimal:
    """
    Multiply two values using Decimal precision
    
    Args:
        a: First value
        b: Second value
        
    Returns:
        Product as Decimal
    """
    return to_decimal(a, "multiplicand") * to_decimal(b, "multiplier")

def decimal_divide(dividend: Union[str, int, float, Decimal], divisor: Union[str, int, float, Decimal]) -> Decimal:
    """
    Divide two values using Decimal precision
    
    Args:
        dividend: Value to be divided
        divisor: Value to divide by
        
    Returns:
        Quotient as Decimal
        
    Raises:
        ValueError: If divisor is zero
    """
    divisor_decimal = to_decimal(divisor, "divisor")
    if divisor_decimal == ZERO:
        raise ValueError("Division by zero")
    
    return to_decimal(dividend, "dividend") / divisor_decimal

def apply_percentage(base_amount: Union[str, int, float, Decimal], percentage: Union[str, int, float, Decimal]) -> Decimal:
    """
    Apply percentage to base amount using Decimal precision
    
    Args:
        base_amount: Base amount to apply percentage to
        percentage: Percentage to apply (e.g., 5.5 for 5.5%)
        
    Returns:
        Result of base_amount * (percentage / 100)
    """
    base_decimal = to_decimal(base_amount, "base_amount")
    percentage_decimal = to_decimal(percentage, "percentage")
    
    return base_decimal * (percentage_decimal / HUNDRED)

def add_percentage(base_amount: Union[str, int, float, Decimal], percentage: Union[str, int, float, Decimal]) -> Decimal:
    """
    Add percentage to base amount (e.g., add 5% markup)
    
    Args:
        base_amount: Base amount
        percentage: Percentage to add (e.g., 5.5 for 5.5%)
        
    Returns:
        base_amount * (1 + percentage/100)
    """
    base_decimal = to_decimal(base_amount, "base_amount")
    percentage_decimal = to_decimal(percentage, "percentage")
    
    multiplier = ONE + (percentage_decimal / HUNDRED)
    return base_decimal * multiplier

def format_currency(amount: Union[str, int, float, Decimal], currency_symbol: str = "$") -> str:
    """
    Format Decimal amount as currency string
    
    Args:
        amount: Amount to format
        currency_symbol: Symbol to use
        
    Returns:
        Formatted currency string
    """
    decimal_amount = to_currency_decimal(amount, "amount")
    return f"{currency_symbol}{decimal_amount:.2f}"

def safe_decimal_conversion(value: Union[str, int, float, Decimal, None], field_name: str) -> Decimal:
    """
    Replacement for safe_decimal_to_float - returns Decimal instead of float
    This maintains precision throughout the calculation pipeline
    
    Args:
        value: Database value to convert
        field_name: Field name for error reporting
        
    Returns:
        Decimal value
    """
    try:
        return to_decimal(value, field_name)
    except Exception as e:
        logger.error(f"❌ DECIMAL_CONVERSION_ERROR: Failed to convert {field_name} value {value} (type: {type(value)}) to Decimal: {e}")
        raise ValueError(f"Invalid {field_name} value: {value}")

# Initialize logging
logger.info("✅ Financial precision module loaded - Decimal context configured for monetary calculations")
logger.info(f"   • Precision: {getcontext().prec} digits")
logger.info(f"   • Rounding: {getcontext().rounding}")