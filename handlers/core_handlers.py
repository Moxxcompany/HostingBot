"""
Core Handlers - Main commands and callback router

Handles:
- Bot commands (/start, /help, etc.)
- Main callback router
- Dashboard and menu display
- Language selection
- Terms acceptance
"""

import logging
from typing import Optional, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.common import (
    safe_edit_message,
    get_user_lang_fast,
    decompress_callback,
    clear_all_dns_wizard_state,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Main Commands
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    from handlers_main import start_command as _handler
    return await _handler(update, context)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command"""
    from handlers_main import cancel_command as _handler
    return await _handler(update, context)


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /profile command"""
    from handlers_main import profile_command as _handler
    return await _handler(update, context)


async def hosting_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /hosting command"""
    from handlers_main import hosting_command as _handler
    return await _handler(update, context)


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /language command"""
    from handlers_main import language_command as _handler
    return await _handler(update, context)


async def dns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /dns command"""
    from handlers_main import dns_command as _handler
    return await _handler(update, context)


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast command (admin)"""
    from handlers_main import broadcast_command as _handler
    return await _handler(update, context)


# ============================================================================
# Main Callback Router
# ============================================================================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback query handler - routes to appropriate handlers"""
    from handlers_main import handle_callback as _handler
    return await _handler(update, context)


# ============================================================================
# Dashboard & Menus
# ============================================================================

async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: Optional[Dict] = None):
    """Show main dashboard"""
    from handlers_main import show_dashboard as _handler
    return await _handler(update, context, user_data)


async def show_personalized_dashboard(query):
    """Show personalized dashboard"""
    from handlers_main import show_personalized_dashboard as _handler
    return await _handler(query)


async def show_main_menu(query):
    """Show main menu"""
    from handlers_main import show_main_menu as _handler
    return await _handler(query)


async def show_profile_interface(query):
    """Show profile interface"""
    from handlers_main import show_profile_interface as _handler
    return await _handler(query)


async def show_contact_support(query):
    """Show contact support info"""
    from handlers_main import show_contact_support as _handler
    return await _handler(query)


async def show_reseller_info(query):
    """Show reseller program info"""
    from handlers_main import show_reseller_info as _handler
    return await _handler(query)


# ============================================================================
# Terms & Onboarding
# ============================================================================

async def show_terms_acceptance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show terms acceptance screen"""
    from handlers_main import show_terms_acceptance as _handler
    return await _handler(update, context)


async def handle_terms_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle terms acceptance callback"""
    from handlers_main import handle_terms_callback as _handler
    return await _handler(update, context)


async def show_terms_or_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show terms or dashboard based on user status"""
    from handlers_main import show_terms_or_dashboard as _handler
    return await _handler(update, context)


async def require_user_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user needs onboarding"""
    from handlers_main import require_user_onboarding as _handler
    return await _handler(update, context)


# ============================================================================
# Language Selection
# ============================================================================

async def show_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show language selection"""
    from handlers_main import show_language_selection as _handler
    return await _handler(update, context)


async def handle_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle language selection callback"""
    from handlers_main import handle_language_selection as _handler
    return await _handler(update, context)


async def handle_language_selection_callback(query, lang_code: str, context: ContextTypes.DEFAULT_TYPE):
    """Handle language selection callback from menu"""
    from handlers_main import handle_language_selection_callback as _handler
    return await _handler(query, lang_code, context)


async def show_language_selection_from_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show language selection from profile"""
    from handlers_main import show_language_selection_from_profile as _handler
    return await _handler(update, context)


async def handle_language_selection_from_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle language selection from profile"""
    from handlers_main import handle_language_selection_from_profile as _handler
    return await _handler(update, context)


# ============================================================================
# Admin Commands
# ============================================================================

async def show_openprovider_accounts(query, context):
    """Show OpenProvider accounts (admin)"""
    from handlers_main import show_openprovider_accounts as _handler
    return await _handler(query, context)


async def handle_validate_openprovider_credentials(query, context):
    """Validate OpenProvider credentials (admin)"""
    from handlers_main import handle_validate_openprovider_credentials as _handler
    return await _handler(query, context)


async def handle_set_default_openprovider_account(query, context, account_id: int):
    """Set default OpenProvider account (admin)"""
    from handlers_main import handle_set_default_openprovider_account as _handler
    return await _handler(query, context, account_id)


async def handle_admin_dns_sync(query, context):
    """Handle admin DNS sync (admin)"""
    from handlers_main import handle_admin_dns_sync as _handler
    return await _handler(query, context)


async def send_broadcast(broadcast_message: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send broadcast message (admin)"""
    from handlers_main import send_broadcast as _handler
    return await _handler(broadcast_message, update, context)
