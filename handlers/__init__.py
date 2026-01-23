"""
Handlers Package - Modular handler organization for HostBay Bot

This package provides a cleaner separation of concerns by grouping
handlers by their functional domain.

Modules:
- common.py: Shared utilities, decorators, and helper functions
- core_handlers.py: Main commands and callback router
- dns_handlers.py: DNS wizard and record management
- domain_handlers.py: Domain registration, linking, management
- hosting_handlers.py: Hosting plans, subscriptions, cPanel
- payment_handlers.py: Wallet, crypto payments, transactions
- rdp_handlers.py: Windows RDP server management

Usage:
    # Import specific handlers
    from handlers.dns_handlers import show_dns_dashboard
    from handlers.hosting_handlers import show_hosting_plans
    
    # Import common utilities
    from handlers.common import safe_edit_message, get_user_lang_fast
    
    # Import core handlers
    from handlers.core_handlers import start_command, handle_callback
"""

__version__ = '2.0.0'
__author__ = 'HostBay'

# Common utilities - always available
from .common import (
    # Message utilities
    safe_edit_message,
    escape_content_for_display,
    escape_html,
    
    # Callback compression
    compress_callback,
    decompress_callback,
    store_callback_token,
    retrieve_callback_token,
    cleanup_expired_tokens,
    
    # DNS callbacks
    create_short_dns_callback,
    resolve_short_dns_callback,
    create_short_dns_nav,
    resolve_short_dns_nav,
    smart_dns_callback,
    
    # Validation
    is_valid_domain,
    validate_domain_name,
    validate_email_format,
    is_valid_nameserver,
    is_ip_proxyable,
    
    # User language
    get_user_lang_fast,
    invalidate_user_lang_cache,
    
    # DNS wizard state
    clear_dns_wizard_state,
    clear_dns_wizard_custom_subdomain_state,
    clear_all_dns_wizard_state,
    get_wizard_state,
    set_wizard_state,
    
    # Region helpers
    get_region_name,
)

# Module references for convenient access
from . import common
from . import core_handlers
from . import dns_handlers
from . import domain_handlers
from . import hosting_handlers
from . import payment_handlers
from . import rdp_handlers

__all__ = [
    # Version info
    '__version__',
    '__author__',
    
    # Common utilities
    'safe_edit_message',
    'escape_content_for_display',
    'escape_html',
    'compress_callback',
    'decompress_callback',
    'store_callback_token',
    'retrieve_callback_token',
    'cleanup_expired_tokens',
    'create_short_dns_callback',
    'resolve_short_dns_callback',
    'create_short_dns_nav',
    'resolve_short_dns_nav',
    'smart_dns_callback',
    'is_valid_domain',
    'validate_domain_name',
    'validate_email_format',
    'is_valid_nameserver',
    'is_ip_proxyable',
    'get_user_lang_fast',
    'invalidate_user_lang_cache',
    'clear_dns_wizard_state',
    'clear_dns_wizard_custom_subdomain_state',
    'clear_all_dns_wizard_state',
    'get_wizard_state',
    'set_wizard_state',
    'get_region_name',
    
    # Modules
    'common',
    'core_handlers',
    'dns_handlers',
    'domain_handlers',
    'hosting_handlers',
    'payment_handlers',
    'rdp_handlers',
]
