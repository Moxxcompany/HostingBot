"""
Common Handler Utilities - Shared functions across all handlers

Contains:
- Message editing utilities
- Content escaping/formatting
- Error message formatting
- Caching decorators
- User language resolution with caching
"""

import logging
import hashlib
import html
import time
from typing import Optional, Dict, Any, Tuple, Literal, List
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

# ============================================================================
# User Language Caching (Context-Level)
# ============================================================================

USER_LANG_CACHE_KEY = '_cached_user_lang'
USER_LANG_CACHE_TS = '_cached_user_lang_ts'
LANG_CACHE_TTL = 3600  # 1 hour


async def get_user_language_fast(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> str:
    """
    Fast user language resolution with context-level caching.
    
    Reduces database calls from 100+ per session to ~1-3.
    
    Args:
        update: Telegram Update object
        context: Bot context
        
    Returns:
        User's language code (defaults to 'en')
    """
    from localization import resolve_user_language, LanguageConfig
    
    user = update.effective_user
    if not user:
        return 'en'
    
    # Check context cache
    if context.user_data:
        cached_lang = context.user_data.get(USER_LANG_CACHE_KEY)
        cached_ts = context.user_data.get(USER_LANG_CACHE_TS, 0)
        
        if cached_lang and (time.time() - cached_ts) < LANG_CACHE_TTL:
            return cached_lang
    
    # Resolve and cache
    try:
        telegram_lang = getattr(user, 'language_code', None)
        user_lang = await resolve_user_language(user.id, telegram_lang)
        
        if context.user_data is not None:
            context.user_data[USER_LANG_CACHE_KEY] = user_lang
            context.user_data[USER_LANG_CACHE_TS] = time.time()
        
        return user_lang
    except Exception as e:
        logger.warning("Language resolution failed: %s", e)
        return 'en'


def invalidate_user_lang_cache(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Invalidate user language cache after language change"""
    if context.user_data:
        context.user_data.pop(USER_LANG_CACHE_KEY, None)
        context.user_data.pop(USER_LANG_CACHE_TS, None)


# ============================================================================
# Message Utilities
# ============================================================================

async def safe_edit_message(
    query,
    message: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = 'HTML'
) -> bool:
    """
    Safely edit a message with error handling for common Telegram issues.
    
    Handles:
    - "Message is not modified" errors
    - "Message to edit not found" errors
    - Rate limiting
    - Network issues
    
    Args:
        query: Telegram CallbackQuery object
        message: New message text
        reply_markup: Optional keyboard markup
        parse_mode: Parse mode (HTML or Markdown)
        
    Returns:
        True if edit succeeded, False otherwise
    """
    try:
        await query.edit_message_text(
            text=message,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        return True
    except Exception as e:
        error_str = str(e).lower()
        
        # Handle "message is not modified" - not really an error
        if "not modified" in error_str:
            logger.debug("Message not modified (identical content)")
            return True
        
        # Handle "message to edit not found"
        if "not found" in error_str or "message_id_invalid" in error_str:
            logger.warning("Message to edit not found - may have been deleted")
            return False
        
        # Handle rate limiting
        if "too many requests" in error_str or "retry_after" in error_str:
            logger.warning("Rate limited by Telegram API")
            return False
        
        # Log other errors
        logger.error("Error editing message: %s", e)
        return False


def create_error_message(error_text: str, user_lang: str = 'en') -> str:
    """
    Create a formatted error message.
    
    Args:
        error_text: The error description
        user_lang: User's language code
        
    Returns:
        Formatted error message HTML
    """
    from localization import t
    
    return f"❌ <b>{t('common_labels.error', user_lang)}</b>\n\n{html.escape(error_text)}"


# ============================================================================
# Content Escaping & Formatting
# ============================================================================

def escape_content_for_display(
    content: str,
    mode: str = "full"
) -> Tuple[str, Literal["HTML", "Markdown"]]:
    """
    Escape content for safe Telegram display.
    
    Args:
        content: Raw content string
        mode: "full" for complete content, "summary" for truncated preview
        
    Returns:
        Tuple of (escaped_content, parse_mode)
    """
    if not content:
        return ("", "HTML")
    
    # Escape HTML special characters
    escaped = html.escape(content)
    
    if mode == "summary":
        # Truncate for preview
        max_len = 50
        if len(escaped) > max_len:
            escaped = escaped[:max_len] + "..."
    
    return (escaped, "HTML")


def escape_html(text: str) -> str:
    """Simple HTML escape helper"""
    if not text:
        return ""
    return html.escape(str(text))


# ============================================================================
# Callback Data Compression
# ============================================================================

# Cache for short DNS callbacks (domain -> hash mapping)
_dns_callback_cache: Dict[str, str] = {}
_dns_callback_reverse: Dict[str, str] = {}


def create_short_dns_callback(domain: str, record_id: str, action: str = "record") -> str:
    """
    Create a shortened callback data string for DNS operations.
    
    Telegram limits callback_data to 64 bytes. This compresses long
    domain names into short hashes.
    
    Args:
        domain: Domain name
        record_id: DNS record ID
        action: Action type
        
    Returns:
        Compressed callback string
    """
    if len(domain) <= 20:
        return f"dns:{domain}:{action}:{record_id}"
    
    # Create hash for long domains
    domain_hash = hashlib.md5(domain.encode()).hexdigest()[:8]
    _dns_callback_cache[domain_hash] = domain
    
    return f"dns:{domain_hash}:{action}:{record_id}"


def resolve_short_dns_callback(short_id: str) -> Optional[Tuple[str, str]]:
    """
    Resolve a shortened DNS callback to full domain name.
    
    Args:
        short_id: Short hash or domain
        
    Returns:
        Tuple of (full_domain, record_id) or None
    """
    if short_id in _dns_callback_cache:
        return (_dns_callback_cache[short_id], short_id)
    return None


def smart_dns_callback(domain: str, path: str, force_compress: bool = False) -> str:
    """
    Create smart callback data that fits within Telegram's 64-byte limit.
    
    Args:
        domain: Domain name
        path: Action path (e.g., "add:A", "view", "record:abc123")
        force_compress: Force compression even for short domains
        
    Returns:
        Callback string (max 64 bytes)
    """
    full_callback = f"dns:{domain}:{path}"
    
    if len(full_callback.encode('utf-8')) <= 64 and not force_compress:
        return full_callback
    
    # Need to compress - hash the domain
    domain_hash = hashlib.md5(domain.encode()).hexdigest()[:8]
    _dns_callback_cache[domain_hash] = domain
    
    compressed = f"dns:{domain_hash}:{path}"
    
    # If still too long, hash the path too
    if len(compressed.encode('utf-8')) > 64:
        path_hash = hashlib.md5(path.encode()).hexdigest()[:6]
        _dns_callback_reverse[path_hash] = path
        compressed = f"dns:{domain_hash}:{path_hash}"
    
    return compressed


# ============================================================================
# Validation Helpers
# ============================================================================

def is_valid_domain(domain_name: str) -> bool:
    """
    Validate domain name format.
    
    Args:
        domain_name: Domain to validate
        
    Returns:
        True if valid domain format
    """
    import re
    
    if not domain_name or not isinstance(domain_name, str):
        return False
    
    domain_name = domain_name.lower().strip()
    
    # Basic format check
    if len(domain_name) < 3 or len(domain_name) > 253:
        return False
    
    if '.' not in domain_name:
        return False
    
    # Character validation
    pattern = r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,}$'
    return bool(re.match(pattern, domain_name))


def is_valid_ip_address(ip: str) -> bool:
    """
    Validate IPv4 address format.
    
    Args:
        ip: IP address string
        
    Returns:
        True if valid IPv4
    """
    if not ip:
        return False
    
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


def is_ip_proxyable(ip_str: str) -> bool:
    """
    Check if an IP address can use Cloudflare proxy.
    
    Private and reserved IPs cannot be proxied.
    
    Args:
        ip_str: IP address string
        
    Returns:
        True if IP can be proxied
    """
    if not is_valid_ip_address(ip_str):
        return False
    
    parts = [int(p) for p in ip_str.split('.')]
    
    # Private ranges
    if parts[0] == 10:  # 10.0.0.0/8
        return False
    if parts[0] == 172 and 16 <= parts[1] <= 31:  # 172.16.0.0/12
        return False
    if parts[0] == 192 and parts[1] == 168:  # 192.168.0.0/16
        return False
    if parts[0] == 127:  # Loopback
        return False
    if parts[0] == 169 and parts[1] == 254:  # Link-local
        return False
    
    return True


# ============================================================================
# Rate Limiting
# ============================================================================

_rate_limit_cache: Dict[str, float] = {}
RATE_LIMIT_WINDOW = 1.0  # 1 second between same operations


def check_rate_limit(user_id: int, operation: str) -> bool:
    """
    Check if an operation is rate-limited.
    
    Args:
        user_id: User's Telegram ID
        operation: Operation identifier
        
    Returns:
        True if allowed, False if rate-limited
    """
    key = f"{user_id}:{operation}"
    current_time = time.time()
    
    last_time = _rate_limit_cache.get(key, 0)
    
    if current_time - last_time < RATE_LIMIT_WINDOW:
        return False
    
    _rate_limit_cache[key] = current_time
    
    # Cleanup old entries periodically
    if len(_rate_limit_cache) > 10000:
        cutoff = current_time - 60
        _rate_limit_cache.clear()  # Simple cleanup
    
    return True


# ============================================================================
# Logging Helpers (Lazy Evaluation)
# ============================================================================

def log_debug(logger_instance, message: str, *args):
    """Log debug message with lazy formatting"""
    if logger_instance.isEnabledFor(logging.DEBUG):
        logger_instance.debug(message, *args)


def log_info(logger_instance, message: str, *args):
    """Log info message with lazy formatting"""
    if logger_instance.isEnabledFor(logging.INFO):
        logger_instance.info(message, *args)


def log_warning(logger_instance, message: str, *args):
    """Log warning message with lazy formatting"""
    logger_instance.warning(message, *args)


def log_error(logger_instance, message: str, *args):
    """Log error message with lazy formatting"""
    logger_instance.error(message, *args)
