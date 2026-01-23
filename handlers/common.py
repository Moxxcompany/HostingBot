"""
Common Handler Utilities - Shared functions across all handlers

Contains:
- Message editing utilities
- Content escaping/formatting
- Callback compression/decompression
- Validation helpers
- User language caching
"""

import logging
import hashlib
import html
import time
import secrets
from typing import Optional, Dict, Any, Tuple, Literal
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

# ============================================================================
# Callback Token Storage (for long callback data compression)
# ============================================================================

_callback_tokens: Dict[str, Dict] = {}
_TOKEN_EXPIRY_SECONDS = 3600  # 1 hour


async def store_callback_token(user_id: int, callback_data: str) -> str:
    """Store callback data and return a short token"""
    token = secrets.token_urlsafe(8)
    _callback_tokens[f"{user_id}:{token}"] = {
        'data': callback_data,
        'created': time.time()
    }
    return token


async def retrieve_callback_token(user_id: int, token: str) -> Optional[str]:
    """Retrieve callback data from token"""
    key = f"{user_id}:{token}"
    entry = _callback_tokens.get(key)
    if entry:
        # Check expiry
        if time.time() - entry['created'] < _TOKEN_EXPIRY_SECONDS:
            return entry['data']
        else:
            # Expired - clean up
            del _callback_tokens[key]
    return None


async def cleanup_expired_tokens():
    """Clean up expired callback tokens"""
    current_time = time.time()
    expired_keys = [
        key for key, entry in _callback_tokens.items()
        if current_time - entry['created'] > _TOKEN_EXPIRY_SECONDS
    ]
    for key in expired_keys:
        del _callback_tokens[key]
    if expired_keys:
        logger.debug("Cleaned up %d expired callback tokens", len(expired_keys))


async def compress_callback(callback_data: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Compress callback data if it exceeds Telegram's 64-byte limit"""
    if len(callback_data.encode('utf-8')) <= 64:
        return callback_data
    
    user_id = context.user_data.get('_user_id', 0) if context.user_data else 0
    token = await store_callback_token(user_id, callback_data)
    return f"tk:{token}"


async def decompress_callback(callback_data: Optional[str], context: ContextTypes.DEFAULT_TYPE) -> str:
    """Decompress callback data if it's a token"""
    if not callback_data:
        return ""
    
    if callback_data.startswith("tk:"):
        token = callback_data[3:]
        user_id = context.user_data.get('_user_id', 0) if context.user_data else 0
        original = await retrieve_callback_token(user_id, token)
        if original:
            return original
        return f"error:expired_token:{token}"
    
    return callback_data


# ============================================================================
# DNS Callback Compression
# ============================================================================

_dns_callback_cache: Dict[str, str] = {}


def create_short_dns_callback(domain: str, record_id: str, action: str = "record") -> str:
    """Create a shortened callback for DNS operations"""
    if len(domain) <= 20:
        return f"dns:{domain}:{action}:{record_id}"
    
    domain_hash = hashlib.md5(domain.encode()).hexdigest()[:8]
    _dns_callback_cache[domain_hash] = domain
    return f"dns:{domain_hash}:{action}:{record_id}"


def resolve_short_dns_callback(short_id: str) -> Optional[Tuple[str, str]]:
    """Resolve shortened DNS callback to full domain"""
    if short_id in _dns_callback_cache:
        return (_dns_callback_cache[short_id], short_id)
    return None


def create_short_dns_nav(domain: str, path: str) -> str:
    """Create short navigation callback for DNS"""
    if len(domain) <= 25:
        return f"dns:{domain}:{path}"
    
    domain_hash = hashlib.md5(domain.encode()).hexdigest()[:8]
    _dns_callback_cache[domain_hash] = domain
    return f"dns:{domain_hash}:{path}"


def resolve_short_dns_nav(short_id: str) -> Optional[Tuple[str, str]]:
    """Resolve short DNS navigation callback"""
    if short_id in _dns_callback_cache:
        return (_dns_callback_cache[short_id], "")
    return None


def smart_dns_callback(domain: str, path: str, force_compress: bool = False) -> str:
    """Create smart callback that fits within 64 bytes"""
    full_callback = f"dns:{domain}:{path}"
    
    if len(full_callback.encode('utf-8')) <= 64 and not force_compress:
        return full_callback
    
    domain_hash = hashlib.md5(domain.encode()).hexdigest()[:8]
    _dns_callback_cache[domain_hash] = domain
    return f"dns:{domain_hash}:{path}"


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
    Safely edit a message with error handling.
    
    Handles common Telegram errors:
    - "Message is not modified"
    - "Message to edit not found"
    - Rate limiting
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
        
        if "not modified" in error_str:
            logger.debug("Message not modified (identical content)")
            return True
        
        if "not found" in error_str or "message_id_invalid" in error_str:
            logger.warning("Message to edit not found")
            return False
        
        if "too many requests" in error_str:
            logger.warning("Rate limited by Telegram API")
            return False
        
        logger.error("Error editing message: %s", e)
        return False


# ============================================================================
# Content Escaping
# ============================================================================

def escape_content_for_display(
    content: str,
    mode: str = "full"
) -> Tuple[str, Literal["HTML", "Markdown"]]:
    """
    Escape content for safe Telegram display.
    
    Args:
        content: Raw content string
        mode: "full" for complete, "summary" for truncated
    
    Returns:
        Tuple of (escaped_content, parse_mode)
    """
    if not content:
        return ("", "HTML")
    
    escaped = html.escape(str(content))
    
    if mode == "summary":
        max_len = 50
        if len(escaped) > max_len:
            escaped = escaped[:max_len] + "..."
    
    return (escaped, "HTML")


def escape_html(text: str) -> str:
    """Simple HTML escape"""
    if not text:
        return ""
    return html.escape(str(text))


# ============================================================================
# Validation Helpers
# ============================================================================

def is_valid_domain(domain_name: str) -> bool:
    """Validate domain name format"""
    import re
    
    if not domain_name or not isinstance(domain_name, str):
        return False
    
    domain_name = domain_name.lower().strip()
    
    if len(domain_name) < 3 or len(domain_name) > 253:
        return False
    
    if '.' not in domain_name:
        return False
    
    pattern = r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,}$'
    return bool(re.match(pattern, domain_name))


def validate_domain_name(domain: str) -> bool:
    """Validate domain name (alias for is_valid_domain)"""
    return is_valid_domain(domain)


def validate_email_format(email: str) -> bool:
    """Validate email format"""
    import re
    
    if not email:
        return False
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def is_valid_nameserver(nameserver: str) -> bool:
    """Validate nameserver format"""
    import re
    
    if not nameserver:
        return False
    
    nameserver = nameserver.lower().strip()
    pattern = r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'
    return bool(re.match(pattern, nameserver))


def is_ip_proxyable(ip_str: str) -> bool:
    """Check if IP can use Cloudflare proxy"""
    if not ip_str:
        return False
    
    parts = ip_str.split('.')
    if len(parts) != 4:
        return False
    
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return False
    
    # Private ranges
    if parts[0] == 10:
        return False
    if parts[0] == 172 and 16 <= parts[1] <= 31:
        return False
    if parts[0] == 192 and parts[1] == 168:
        return False
    if parts[0] == 127:
        return False
    if parts[0] == 169 and parts[1] == 254:
        return False
    
    return True


# ============================================================================
# User Language Caching
# ============================================================================

async def get_user_lang_fast(user, context: ContextTypes.DEFAULT_TYPE = None) -> str:
    """
    Fast user language resolution with context-level caching.
    
    Reduces database calls from 100+/session to ~1-3.
    """
    from localization import resolve_user_language
    
    if not user:
        return 'en'
    
    user_id = user.id
    telegram_lang = getattr(user, 'language_code', None)
    
    if context and context.user_data is not None:
        cached = context.user_data.get('_cached_user_lang')
        cached_ts = context.user_data.get('_cached_user_lang_ts', 0)
        
        if cached and (time.time() - cached_ts) < 3600:
            return cached
        
        user_lang = await resolve_user_language(user_id, telegram_lang)
        context.user_data['_cached_user_lang'] = user_lang
        context.user_data['_cached_user_lang_ts'] = time.time()
        return user_lang
    
    return await resolve_user_language(user_id, telegram_lang)


def invalidate_user_lang_cache(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Invalidate user language cache after language change"""
    if context.user_data:
        context.user_data.pop('_cached_user_lang', None)
        context.user_data.pop('_cached_user_lang_ts', None)


# ============================================================================
# DNS Wizard State Management
# ============================================================================

def clear_dns_wizard_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear DNS wizard state from context"""
    if context.user_data:
        context.user_data.pop('dns_wizard', None)


def clear_dns_wizard_custom_subdomain_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear custom subdomain input flags"""
    if context.user_data:
        for key in list(context.user_data.keys()):
            if key.startswith('expecting_custom_subdomain'):
                del context.user_data[key]


def clear_all_dns_wizard_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear all DNS-related wizard state"""
    clear_dns_wizard_state(context)
    clear_dns_wizard_custom_subdomain_state(context)
    
    if context.user_data:
        keys_to_clear = [
            'expecting_dns_content_input',
            'expecting_dns_ip_input',
            'dns_record_edit',
            'dns_edit_input',
        ]
        for key in keys_to_clear:
            context.user_data.pop(key, None)


def get_wizard_state(context: ContextTypes.DEFAULT_TYPE) -> Optional[Dict]:
    """Get current DNS wizard state"""
    if context.user_data:
        return context.user_data.get('dns_wizard')
    return None


def set_wizard_state(context: ContextTypes.DEFAULT_TYPE, state: Dict) -> None:
    """Set DNS wizard state"""
    if context.user_data is not None:
        context.user_data['dns_wizard'] = state


# ============================================================================
# Region Helpers
# ============================================================================

_region_cache = {}

def get_region_name(region_code: str) -> str:
    """Convert region code to readable name"""
    if region_code in _region_cache:
        return _region_cache[region_code]
    
    region_map = {
        'ewr': 'Newark, US',
        'ord': 'Chicago, US',
        'dfw': 'Dallas, US',
        'sea': 'Seattle, US',
        'lax': 'Los Angeles, US',
        'atl': 'Atlanta, US',
        'ams': 'Amsterdam, NL',
        'lhr': 'London, UK',
        'fra': 'Frankfurt, DE',
        'cdg': 'Paris, FR',
        'nrt': 'Tokyo, JP',
        'sgp': 'Singapore',
        'syd': 'Sydney, AU',
        'yto': 'Toronto, CA',
        'mia': 'Miami, US',
    }
    
    name = region_map.get(region_code.lower(), region_code.upper())
    _region_cache[region_code] = name
    return name
