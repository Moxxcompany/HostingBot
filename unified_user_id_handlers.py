"""
UNIFIED TELEGRAM ID HANDLERS - ONE WAY APPROACH
================================================

This module provides standardized functions for handling Telegram ID conversions
and user lookups throughout the HostBay system. It eliminates confusion between
external telegram_id (from Telegram API) and internal user_id (database primary key).

DESIGN PRINCIPLES:
1. Clear function names that indicate which ID type they expect/return
2. Consistent parameter naming: telegram_id vs internal_user_id
3. Centralized conversion logic with error handling
4. Type safety and validation

ID TYPES:
- telegram_id (BIGINT): External identifier from Telegram API (e.g., 123456789)
- internal_user_id (INTEGER): Internal database primary key from users.id (e.g., 1, 2, 3)
"""

import logging
from typing import Optional, Dict, Any, Union
from database import execute_query, get_or_create_user as db_get_or_create_user

logger = logging.getLogger(__name__)

class UserIdError(Exception):
    """Raised when user ID conversion or lookup fails"""
    pass

# ==============================================================================
# CORE USER LOOKUP AND CONVERSION FUNCTIONS
# ==============================================================================

async def get_internal_user_id_from_telegram_id(telegram_id: int, raise_on_error: bool = False) -> Optional[int]:
    """
    Convert external Telegram ID to internal database user ID.
    
    Args:
        telegram_id: Telegram user ID (BIGINT from Telegram API)
        raise_on_error: If True, raises UserIdError on database errors (default: False)
        
    Returns:
        Internal user ID (INTEGER primary key) or None if not found
        
    Raises:
        UserIdError: If raise_on_error=True and database error occurs
        
    Example:
        internal_id = await get_internal_user_id_from_telegram_id(123456789)
        # Returns: 5 (users.id primary key) or None if not found
        
        # For critical operations that need error handling:
        internal_id = await get_internal_user_id_from_telegram_id(123456789, raise_on_error=True)
        # Returns: 5 or raises UserIdError on database failure
    """
    try:
        result = await execute_query(
            "SELECT id FROM users WHERE telegram_id = %s",
            (telegram_id,)
        )
        if result:
            return result[0]['id']
        return None  # User not found (not an error)
    except Exception as e:
        logger.error(f"❌ DATABASE ERROR converting telegram_id {telegram_id} to internal_user_id: {e}")
        if raise_on_error:
            raise UserIdError(f"Database error during ID conversion: {e}")
        return None

async def get_telegram_id_from_internal_user_id(internal_user_id: int) -> Optional[int]:
    """
    Convert internal database user ID to external Telegram ID.
    
    Args:
        internal_user_id: Internal user ID (INTEGER from users.id)
        
    Returns:
        Telegram ID (BIGINT) or None if not found
        
    Example:
        telegram_id = await get_telegram_id_from_internal_user_id(5)
        # Returns: 123456789 (telegram_id from Telegram API)
    """
    try:
        result = await execute_query(
            "SELECT telegram_id FROM users WHERE id = %s",
            (internal_user_id,)
        )
        if result:
            return result[0]['telegram_id']
        return None
    except Exception as e:
        logger.error(f"❌ Failed to convert internal_user_id {internal_user_id} to telegram_id: {e}")
        return None

async def ensure_user_exists_by_telegram_id(telegram_id: int, username: Optional[str] = None, 
                                           first_name: Optional[str] = None, last_name: Optional[str] = None) -> int:
    """
    Ensure user exists in database and return internal user ID.
    Creates user if doesn't exist.
    
    Args:
        telegram_id: Telegram user ID (BIGINT from Telegram API)
        username: Optional username for creation
        first_name: Optional first name for creation
        last_name: Optional last name for creation
        
    Returns:
        Internal user ID (INTEGER from users.id)
        
    Raises:
        UserIdError: If user creation fails
        
    Example:
        user_id = await ensure_user_exists_by_telegram_id(123456789, 
            username='john_doe', first_name='John')
        # Returns: 5 (guaranteed to exist in database)
    """
    try:
        # Use existing database function with keyword arguments to match exact signature
        user_record = await db_get_or_create_user(
            telegram_id=telegram_id, 
            username=username, 
            first_name=first_name, 
            last_name=last_name
        )
        if user_record and 'id' in user_record:
            return user_record['id']
        else:
            raise UserIdError(f"Failed to create or retrieve user for telegram_id {telegram_id}")
    except Exception as e:
        logger.error(f"❌ Failed to ensure user exists for telegram_id {telegram_id}: {e}")
        raise UserIdError(f"User creation/lookup failed: {e}")

# ==============================================================================
# STANDARDIZED WALLET OPERATIONS WITH CLEAR ID TYPES
# ==============================================================================

async def get_wallet_balance_by_telegram_id(telegram_id: int) -> float:
    """
    Get wallet balance using external Telegram ID.
    
    Args:
        telegram_id: Telegram user ID (BIGINT from Telegram API)
        
    Returns:
        Wallet balance as float, 0.00 if user not found
        
    Example:
        balance = await get_wallet_balance_by_telegram_id(123456789)
        # Returns: 25.50
    """
    try:
        result = await execute_query(
            "SELECT wallet_balance FROM users WHERE telegram_id = %s", 
            (telegram_id,)
        )
        if result:
            return float(result[0]['wallet_balance'] or 0.00)
        return 0.00
    except Exception as e:
        logger.error(f"❌ Failed to get wallet balance for telegram_id {telegram_id}: {e}")
        return 0.00

async def get_wallet_balance_by_internal_user_id(internal_user_id: int) -> float:
    """
    Get wallet balance using internal database user ID.
    
    Args:
        internal_user_id: Internal user ID (INTEGER from users.id)
        
    Returns:
        Wallet balance as float, 0.00 if user not found
        
    Example:
        balance = await get_wallet_balance_by_internal_user_id(5)
        # Returns: 25.50
    """
    try:
        result = await execute_query(
            "SELECT wallet_balance FROM users WHERE id = %s", 
            (internal_user_id,)
        )
        if result:
            return float(result[0]['wallet_balance'] or 0.00)
        return 0.00
    except Exception as e:
        logger.error(f"❌ Failed to get wallet balance for internal_user_id {internal_user_id}: {e}")
        return 0.00

# ==============================================================================
# UNIFIED USER DATA RETRIEVAL FUNCTIONS
# ==============================================================================

async def get_user_data_by_telegram_id(telegram_id: int) -> Optional[Dict[str, Any]]:
    """
    Get complete user record using external Telegram ID.
    
    Args:
        telegram_id: Telegram user ID (BIGINT from Telegram API)
        
    Returns:
        Complete user record dict or None if not found
        
    Example:
        user_data = await get_user_data_by_telegram_id(123456789)
        # Returns: {'id': 5, 'telegram_id': 123456789, 'username': 'john_doe', ...}
    """
    try:
        result = await execute_query(
            "SELECT * FROM users WHERE telegram_id = %s",
            (telegram_id,)
        )
        return result[0] if result else None
    except Exception as e:
        logger.error(f"❌ Failed to get user data for telegram_id {telegram_id}: {e}")
        return None

async def get_user_data_by_internal_user_id(internal_user_id: int) -> Optional[Dict[str, Any]]:
    """
    Get complete user record using internal database user ID.
    
    Args:
        internal_user_id: Internal user ID (INTEGER from users.id)
        
    Returns:
        Complete user record dict or None if not found
        
    Example:
        user_data = await get_user_data_by_internal_user_id(5)
        # Returns: {'id': 5, 'telegram_id': 123456789, 'username': 'john_doe', ...}
    """
    try:
        result = await execute_query(
            "SELECT * FROM users WHERE id = %s",
            (internal_user_id,)
        )
        return result[0] if result else None
    except Exception as e:
        logger.error(f"❌ Failed to get user data for internal_user_id {internal_user_id}: {e}")
        return None

# ==============================================================================
# VALIDATION AND UTILITY FUNCTIONS
# ==============================================================================

def validate_telegram_id(telegram_id: Union[int, str]) -> int:
    """
    Validate and convert Telegram ID to integer.
    
    Args:
        telegram_id: Telegram ID as int or string
        
    Returns:
        Validated Telegram ID as integer
        
    Raises:
        UserIdError: If validation fails
        
    Example:
        valid_id = validate_telegram_id("123456789")
        # Returns: 123456789
    """
    try:
        telegram_id_int = int(telegram_id)
        if telegram_id_int <= 0:
            raise UserIdError(f"Invalid Telegram ID: must be positive integer, got {telegram_id_int}")
        if telegram_id_int > 2**63 - 1:  # BIGINT max value
            raise UserIdError(f"Invalid Telegram ID: exceeds BIGINT range, got {telegram_id_int}")
        return telegram_id_int
    except ValueError:
        raise UserIdError(f"Invalid Telegram ID format: cannot convert '{telegram_id}' to integer")

def validate_internal_user_id(internal_user_id: Union[int, str]) -> int:
    """
    Validate and convert internal user ID to integer.
    
    Args:
        internal_user_id: Internal user ID as int or string
        
    Returns:
        Validated internal user ID as integer
        
    Raises:
        UserIdError: If validation fails
        
    Example:
        valid_id = validate_internal_user_id("5")
        # Returns: 5
    """
    try:
        user_id_int = int(internal_user_id)
        if user_id_int <= 0:
            raise UserIdError(f"Invalid internal user ID: must be positive integer, got {user_id_int}")
        if user_id_int > 2**31 - 1:  # INTEGER max value
            raise UserIdError(f"Invalid internal user ID: exceeds INTEGER range, got {user_id_int}")
        return user_id_int
    except ValueError:
        raise UserIdError(f"Invalid internal user ID format: cannot convert '{internal_user_id}' to integer")

# ==============================================================================
# MIGRATION HELPERS - FOR UPDATING EXISTING CODE
# ==============================================================================

async def migrate_function_call_telegram_id_to_internal(telegram_id: int) -> Optional[int]:
    """
    Helper function to migrate existing code that needs internal_user_id.
    
    This function helps update existing code that currently uses telegram_id
    but should be using internal_user_id for database operations.
    
    Args:
        telegram_id: Telegram user ID (BIGINT from Telegram API)
        
    Returns:
        Internal user ID (INTEGER) or None if user not found
        
    Usage:
        # Old code:
        # result = await some_function(telegram_id)
        
        # New code:
        # internal_id = await migrate_function_call_telegram_id_to_internal(telegram_id)
        # if internal_id:
        #     result = await some_function(internal_id)
    """
    logger.warning(f"📝 MIGRATION: Converting telegram_id {telegram_id} to internal_user_id")
    return await get_internal_user_id_from_telegram_id(telegram_id)

# ==============================================================================
# USAGE EXAMPLES AND BEST PRACTICES
# ==============================================================================

"""
BEST PRACTICES FOR USING THIS MODULE:

1. **Function Parameters**: Always use descriptive parameter names:
   ✅ Good: def my_function(telegram_id: int, internal_user_id: int)
   ❌ Bad:  def my_function(user_id: int)  # Ambiguous!

2. **Database Operations**: Use internal_user_id for foreign keys:
   ✅ Good: INSERT INTO orders (user_id, ...) VALUES (internal_user_id, ...)
   ❌ Bad:  INSERT INTO orders (user_id, ...) VALUES (telegram_id, ...)

3. **Telegram API**: Use telegram_id for Telegram operations:
   ✅ Good: await bot.send_message(chat_id=telegram_id, text="...")
   ❌ Bad:  await bot.send_message(chat_id=internal_user_id, text="...")

4. **User Lookup**: Choose the right function for your input:
   - Have telegram_id? Use get_user_data_by_telegram_id()
   - Have internal_user_id? Use get_user_data_by_internal_user_id()

5. **Error Handling**: Always handle None returns and exceptions:
   user_data = await get_user_data_by_telegram_id(telegram_id)
   if not user_data:
       logger.error(f"User not found for telegram_id {telegram_id}")
       return

MIGRATION GUIDE:

Replace these patterns:
- get_or_create_user() → ensure_user_exists_by_telegram_id()
- get_user_wallet_balance() → get_wallet_balance_by_telegram_id()
- get_user_wallet_balance_by_id() → get_wallet_balance_by_internal_user_id()
- get_telegram_id_from_user_id() → get_telegram_id_from_internal_user_id()

This provides a clear, consistent API for user ID handling across the entire system.
"""