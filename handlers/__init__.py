"""
Handlers Package - Modular handler organization for HostBay Bot

This package provides a cleaner separation of concerns by grouping
handlers by their functional domain.

Structure:
- common.py: Shared utilities, decorators, and helper functions
- dns_handlers.py: DNS wizard and record management
- domain_handlers.py: Domain registration, linking, management
- hosting_handlers.py: Hosting plans, subscriptions, cPanel
- payment_handlers.py: Wallet, crypto payments, transactions
- rdp_handlers.py: Windows RDP server management
- admin_handlers.py: Admin panel operations

Usage:
    from handlers import (
        start_command,
        handle_callback,
        dns_handlers,
        domain_handlers
    )
    
    # Or import specific handlers
    from handlers.dns_handlers import handle_dns_wizard_callback
"""

# Re-export main handlers for backward compatibility
# These imports will be added as handlers are modularized

# Version info
__version__ = '2.0.0'
__author__ = 'HostBay'

# Import common utilities
from .common import (
    safe_edit_message,
    escape_content_for_display,
    create_error_message,
    get_user_language_fast,
)

# Note: Full handler imports will be added after modularization
# For now, the main handlers.py file is still the primary source

__all__ = [
    'safe_edit_message',
    'escape_content_for_display', 
    'create_error_message',
    'get_user_language_fast',
]
