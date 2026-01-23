"""
Keyboard Cache - High-performance caching for Telegram inline keyboards

Caches static and semi-static keyboard layouts to avoid rebuilding on every callback.
Significantly reduces latency for frequently-used keyboard patterns.
"""

import hashlib
import logging
from typing import Dict, List, Optional, Any, Tuple
from functools import lru_cache
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

# Global keyboard cache with LRU eviction
_keyboard_cache: Dict[str, InlineKeyboardMarkup] = {}
_cache_stats = {'hits': 0, 'misses': 0}


def _generate_cache_key(*args, **kwargs) -> str:
    """Generate a deterministic cache key from arguments"""
    key_parts = [str(arg) for arg in args]
    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    key_string = "|".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()[:16]


def get_cached_keyboard(cache_key: str) -> Optional[InlineKeyboardMarkup]:
    """Get keyboard from cache if available"""
    global _cache_stats
    if cache_key in _keyboard_cache:
        _cache_stats['hits'] += 1
        return _keyboard_cache[cache_key]
    _cache_stats['misses'] += 1
    return None


def cache_keyboard(cache_key: str, keyboard: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    """Cache a keyboard and return it"""
    # Limit cache size to prevent memory issues
    if len(_keyboard_cache) > 500:
        # Remove oldest 100 entries (simple eviction)
        keys_to_remove = list(_keyboard_cache.keys())[:100]
        for key in keys_to_remove:
            _keyboard_cache.pop(key, None)
        logger.debug(f"🧹 Keyboard cache cleanup: removed {len(keys_to_remove)} entries")
    
    _keyboard_cache[cache_key] = keyboard
    return keyboard


def get_cache_stats() -> Dict[str, Any]:
    """Get keyboard cache statistics"""
    total = _cache_stats['hits'] + _cache_stats['misses']
    hit_rate = (_cache_stats['hits'] / total * 100) if total > 0 else 0
    return {
        'entries': len(_keyboard_cache),
        'hits': _cache_stats['hits'],
        'misses': _cache_stats['misses'],
        'hit_rate': f"{hit_rate:.1f}%"
    }


def clear_keyboard_cache():
    """Clear all cached keyboards"""
    global _keyboard_cache
    count = len(_keyboard_cache)
    _keyboard_cache.clear()
    logger.info(f"🗑️ Cleared {count} cached keyboards")


# ============================================================================
# Pre-built keyboard factories with caching
# ============================================================================

def get_dns_record_type_keyboard(domain: str, user_lang: str) -> InlineKeyboardMarkup:
    """Get cached DNS record type selection keyboard"""
    from localization import t
    
    cache_key = f"dns_types:{domain}:{user_lang}"
    cached = get_cached_keyboard(cache_key)
    if cached:
        return cached
    
    # Smart callback data to fit Telegram's 64-byte limit
    def smart_dns_callback(domain: str, action: str) -> str:
        if len(domain) > 30:
            domain_hash = hashlib.md5(domain.encode()).hexdigest()[:8]
            return f"dns:{domain_hash}:{action}"
        return f"dns:{domain}:{action}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("buttons.a_record", user_lang), callback_data=smart_dns_callback(domain, "add:A")),
         InlineKeyboardButton(t("buttons.cname_record", user_lang), callback_data=smart_dns_callback(domain, "add:CNAME"))],
        [InlineKeyboardButton(t("buttons.txt_record", user_lang), callback_data=smart_dns_callback(domain, "add:TXT")),
         InlineKeyboardButton(t("buttons.mx_record", user_lang), callback_data=smart_dns_callback(domain, "add:MX"))],
        [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=smart_dns_callback(domain, "view"))]
    ])
    
    return cache_keyboard(cache_key, keyboard)


def get_ttl_selection_keyboard(domain: str, record_type: str, user_lang: str, back_field: str = "name") -> InlineKeyboardMarkup:
    """Get cached TTL selection keyboard"""
    from localization import t
    
    cache_key = f"ttl_select:{domain}:{record_type}:{user_lang}:{back_field}"
    cached = get_cached_keyboard(cache_key)
    if cached:
        return cached
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("buttons.auto_recommended_label", user_lang), callback_data=f"dns_wizard:{domain}:{record_type}:ttl:1")],
        [InlineKeyboardButton(t("buttons.5_minutes_label", user_lang), callback_data=f"dns_wizard:{domain}:{record_type}:ttl:300")],
        [InlineKeyboardButton(t("buttons.1_hour_label", user_lang), callback_data=f"dns_wizard:{domain}:{record_type}:ttl:3600"),
         InlineKeyboardButton(t("buttons.1_day", user_lang), callback_data=f"dns_wizard:{domain}:{record_type}:ttl:86400")],
        [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:{record_type}:{back_field}:back")]
    ])
    
    return cache_keyboard(cache_key, keyboard)


def get_mx_priority_keyboard(domain: str, user_lang: str) -> InlineKeyboardMarkup:
    """Get cached MX priority selection keyboard"""
    from localization import t
    
    cache_key = f"mx_priority:{domain}:{user_lang}"
    cached = get_cached_keyboard(cache_key)
    if cached:
        return cached
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("buttons.priority_10", user_lang), callback_data=f"dns_wizard:{domain}:MX:priority:10")],
        [InlineKeyboardButton(t("buttons.priority_20", user_lang), callback_data=f"dns_wizard:{domain}:MX:priority:20"),
         InlineKeyboardButton(t("buttons.priority_30", user_lang), callback_data=f"dns_wizard:{domain}:MX:priority:30")],
        [InlineKeyboardButton(t("buttons.priority_0", user_lang), callback_data=f"dns_wizard:{domain}:MX:priority:0"),
         InlineKeyboardButton(t("buttons.priority_50", user_lang), callback_data=f"dns_wizard:{domain}:MX:priority:50")],
        [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:MX:server:back")]
    ])
    
    return cache_keyboard(cache_key, keyboard)


def get_proxy_selection_keyboard(domain: str, user_lang: str, can_proxy: bool = True) -> InlineKeyboardMarkup:
    """Get cached proxy selection keyboard for A records"""
    from localization import t
    
    cache_key = f"proxy_select:{domain}:{user_lang}:{can_proxy}"
    cached = get_cached_keyboard(cache_key)
    if cached:
        return cached
    
    if can_proxy:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(t("buttons.proxied_recommended", user_lang), callback_data=f"dns_wizard:{domain}:A:proxied:true")],
            [InlineKeyboardButton(t("buttons.direct", user_lang), callback_data=f"dns_wizard:{domain}:A:proxied:false")],
            [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:A:ttl:back")]
        ])
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(t("buttons.direct_only_option", user_lang), callback_data=f"dns_wizard:{domain}:A:proxied:false")],
            [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:A:ttl:back")]
        ])
    
    return cache_keyboard(cache_key, keyboard)


def get_language_selection_keyboard(user_lang: str) -> InlineKeyboardMarkup:
    """Get cached language selection keyboard"""
    from localization import t, get_supported_languages
    
    cache_key = f"lang_select:{user_lang}"
    cached = get_cached_keyboard(cache_key)
    if cached:
        return cached
    
    languages = get_supported_languages()
    keyboard_buttons = []
    
    for lang_code, lang_name in languages.items():
        # Add checkmark for current language
        display_name = f"✓ {lang_name}" if lang_code == user_lang else lang_name
        keyboard_buttons.append([
            InlineKeyboardButton(display_name, callback_data=f"lang:{lang_code}")
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(t("buttons.back", user_lang), callback_data="settings:back")
    ])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    return cache_keyboard(cache_key, keyboard)


def get_main_menu_keyboard(user_lang: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    """Get cached main menu keyboard"""
    from localization import t
    
    cache_key = f"main_menu:{user_lang}:{is_admin}"
    cached = get_cached_keyboard(cache_key)
    if cached:
        return cached
    
    keyboard_buttons = [
        [InlineKeyboardButton(t("buttons.my_domains", user_lang), callback_data="domains:list"),
         InlineKeyboardButton(t("buttons.register_domain", user_lang), callback_data="domains:register")],
        [InlineKeyboardButton(t("buttons.hosting", user_lang), callback_data="hosting:plans"),
         InlineKeyboardButton(t("buttons.rdp", user_lang), callback_data="rdp:plans")],
        [InlineKeyboardButton(t("buttons.wallet", user_lang), callback_data="wallet:view"),
         InlineKeyboardButton(t("buttons.settings", user_lang), callback_data="settings:view")]
    ]
    
    if is_admin:
        keyboard_buttons.append([
            InlineKeyboardButton(t("buttons.admin_panel", user_lang), callback_data="admin:panel")
        ])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    return cache_keyboard(cache_key, keyboard)


def get_confirmation_keyboard(
    domain: str, 
    action: str, 
    user_lang: str,
    confirm_callback: str,
    cancel_callback: str
) -> InlineKeyboardMarkup:
    """Get cached confirmation keyboard"""
    from localization import t
    
    cache_key = f"confirm:{domain}:{action}:{user_lang}"
    cached = get_cached_keyboard(cache_key)
    if cached:
        return cached
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("buttons.confirm", user_lang), callback_data=confirm_callback)],
        [InlineKeyboardButton(t("buttons.cancel", user_lang), callback_data=cancel_callback)]
    ])
    
    return cache_keyboard(cache_key, keyboard)
