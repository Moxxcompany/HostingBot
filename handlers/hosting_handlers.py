"""
Hosting Handlers - Web hosting management functionality

Handles:
- Hosting plan display and selection
- cPanel account management
- Subscription management
- Hosting renewals
- Usage monitoring
"""

import logging
from typing import Optional, Dict, List, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.common import (
    safe_edit_message,
    escape_html,
    get_user_lang_fast,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Hosting Plans & Interface
# ============================================================================

async def show_hosting_interface(query, context=None):
    """Show main hosting interface"""
    # Import from main handlers to avoid duplication during transition
    from handlers_main import show_hosting_interface as _show_hosting_interface
    return await _show_hosting_interface(query, context)


async def show_hosting_plans(query):
    """Show available hosting plans"""
    from handlers_main import show_hosting_plans as _show_hosting_plans
    return await _show_hosting_plans(query)


async def show_hosting_management(query, subscription_id: str):
    """Show hosting account management interface"""
    from handlers_main import show_hosting_management as _show_hosting_management
    return await _show_hosting_management(query, subscription_id)


async def show_hosting_details(query, subscription_id: str):
    """Show hosting subscription details"""
    from handlers_main import show_hosting_details as _show_hosting_details
    return await _show_hosting_details(query, subscription_id)


async def show_cpanel_login(query, subscription_id: str):
    """Show cPanel login credentials"""
    from handlers_main import show_cpanel_login as _show_cpanel_login
    return await _show_cpanel_login(query, subscription_id)


async def show_hosting_usage(query, subscription_id: str):
    """Show hosting resource usage"""
    from handlers_main import show_hosting_usage as _show_hosting_usage
    return await _show_hosting_usage(query, subscription_id)


# ============================================================================
# Hosting Lifecycle Management
# ============================================================================

async def handle_renew_suspended_hosting(query, subscription_id: str):
    """Handle renewal of suspended hosting"""
    from handlers_main import handle_renew_suspended_hosting as _handler
    return await _handler(query, subscription_id)


async def handle_manual_renewal(query, subscription_id: str):
    """Handle manual hosting renewal"""
    from handlers_main import handle_manual_renewal as _handler
    return await _handler(query, subscription_id)


async def process_manual_renewal_wallet(query, subscription_id: str):
    """Process wallet payment for renewal"""
    from handlers_main import process_manual_renewal_wallet as _handler
    return await _handler(query, subscription_id)


async def process_manual_renewal_crypto(query, subscription_id: str):
    """Process crypto payment for renewal"""
    from handlers_main import process_manual_renewal_crypto as _handler
    return await _handler(query, subscription_id)


async def suspend_hosting_account(query, subscription_id: str):
    """Suspend hosting account"""
    from handlers_main import suspend_hosting_account as _handler
    return await _handler(query, subscription_id)


async def confirm_hosting_suspension(query, subscription_id: str):
    """Confirm hosting suspension"""
    from handlers_main import confirm_hosting_suspension as _handler
    return await _handler(query, subscription_id)


async def unsuspend_hosting_account(query, subscription_id: str):
    """Unsuspend hosting account"""
    from handlers_main import unsuspend_hosting_account as _handler
    return await _handler(query, subscription_id)


async def restart_hosting_services(query, subscription_id: str):
    """Restart hosting services"""
    from handlers_main import restart_hosting_services as _handler
    return await _handler(query, subscription_id)


async def check_hosting_status(query, subscription_id: str):
    """Check hosting account status"""
    from handlers_main import check_hosting_status as _handler
    return await _handler(query, subscription_id)


# ============================================================================
# Unified Hosting Flow
# ============================================================================

async def handle_unified_hosting_only(query, context, plan_id: str):
    """Handle hosting-only purchase flow"""
    from handlers_main import handle_unified_hosting_only as _handler
    return await _handler(query, context, plan_id)


async def process_unified_wallet_payment(query, subscription_id: str, price: str):
    """Process unified wallet payment"""
    from handlers_main import process_unified_wallet_payment as _handler
    return await _handler(query, subscription_id, price)


async def process_unified_crypto_payment(query, crypto_type: str, subscription_id: str, price: str):
    """Process unified crypto payment"""
    from handlers_main import process_unified_crypto_payment as _handler
    return await _handler(query, crypto_type, subscription_id, price)


async def create_unified_hosting_account_after_payment(subscription_id: int):
    """Create hosting account after payment"""
    from handlers_main import create_unified_hosting_account_after_payment as _handler
    return await _handler(subscription_id)


# ============================================================================
# Helper Functions
# ============================================================================

def get_hosting_nameservers() -> list:
    """Get hosting nameservers"""
    from handlers_main import get_hosting_nameservers as _func
    return _func()


def get_hosting_status_description(status: str, user_lang: str) -> str:
    """Get hosting status description"""
    from handlers_main import get_hosting_status_description as _func
    return _func(status, user_lang)


async def show_insufficient_funds_message(query, subscription_id: str):
    """Show insufficient funds message"""
    from handlers_main import show_insufficient_funds_message as _handler
    return await _handler(query, subscription_id)
