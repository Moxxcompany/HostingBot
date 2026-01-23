"""
Utility modules for type conversion, logging, email, timezone, and environment handling.

Performance utilities:
- keyboard_cache: High-performance Telegram keyboard caching
- user_context: User language and context caching
- lazy_logger: Performance-optimized logging utilities
"""

# Import performance utilities
try:
    from .keyboard_cache import (
        get_cached_keyboard,
        cache_keyboard,
        clear_keyboard_cache,
        get_cache_stats,
        get_dns_record_type_keyboard,
        get_ttl_selection_keyboard,
        get_mx_priority_keyboard,
        get_main_menu_keyboard,
    )
except ImportError:
    pass

try:
    from .user_context import (
        get_user_language_cached,
        get_user_context_cached,
        invalidate_user_language_cache,
        clear_user_context_cache,
        with_user_lang,
        with_user_context,
    )
except ImportError:
    pass

try:
    from .lazy_logger import (
        LazyLogger,
        get_lazy_logger,
        get_cached_lazy_logger,
        log_function_call,
        timed_operation,
    )
except ImportError:
    pass