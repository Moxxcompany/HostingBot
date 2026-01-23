"""
Domain Handlers - Domain registration and management

Handles:
- Domain search and availability
- Domain registration flow
- Domain linking (external domains)
- Domain management dashboard
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
    is_valid_domain,
    validate_domain_name,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Domain Search
# ============================================================================

async def show_search_interface(query):
    """Show domain search interface"""
    from handlers import show_search_interface as _handler
    return await _handler(query)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search command"""
    from handlers import search_command as _handler
    return await _handler(update, context)


async def handle_domain_search(update: Update, context: ContextTypes.DEFAULT_TYPE, domain_name: str):
    """Handle domain search input"""
    from handlers import handle_domain_search as _handler
    return await _handler(update, context, domain_name)


async def show_domain_search_results(query, domain_name: str, context):
    """Show domain search results"""
    from handlers import show_domain_search_results as _handler
    return await _handler(query, domain_name, context)


# ============================================================================
# Domain Registration
# ============================================================================

async def start_domain_registration(query, context, domain_name: str):
    """Start domain registration flow"""
    from handlers import start_domain_registration as _handler
    return await _handler(query, context, domain_name)


async def show_domain_registration_payment(query, domain_name: str, price: float, context):
    """Show domain registration payment options"""
    from handlers import show_domain_registration_payment as _handler
    return await _handler(query, domain_name, price, context)


async def process_domain_registration_wallet(query, domain_name: str, context):
    """Process domain registration with wallet payment"""
    from handlers import process_domain_registration_wallet as _handler
    return await _handler(query, domain_name, context)


async def process_domain_registration_crypto(query, domain_name: str, crypto_type: str, context):
    """Process domain registration with crypto payment"""
    from handlers import process_domain_registration_crypto as _handler
    return await _handler(query, domain_name, crypto_type, context)


# ============================================================================
# User Domains
# ============================================================================

async def show_user_domains(query):
    """Show user's domains (simple list)"""
    from handlers import show_user_domains as _handler
    return await _handler(query)


async def show_user_domains_complete(query, context=None):
    """Show user's domains with full details"""
    from handlers import show_user_domains_complete as _handler
    return await _handler(query, context)


async def domain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /domains command"""
    from handlers import domain_command as _handler
    return await _handler(update, context)


# ============================================================================
# Domain Management
# ============================================================================

async def show_domain_management(query, domain_name: str, context):
    """Show domain management dashboard"""
    from handlers import show_domain_management as _handler
    return await _handler(query, domain_name, context)


async def show_domain_details(query, domain_name: str):
    """Show domain details"""
    from handlers import show_domain_details as _handler
    return await _handler(query, domain_name)


async def show_domain_renewal_options(query, domain_name: str, context):
    """Show domain renewal options"""
    from handlers import show_domain_renewal_options as _handler
    return await _handler(query, domain_name, context)


# ============================================================================
# Domain Linking (External Domains)
# ============================================================================

async def link_domain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /link command"""
    from handlers import link_domain_command as _handler
    return await _handler(update, context)


async def show_domain_linking_intro(user, message, user_lang: str):
    """Show domain linking introduction"""
    from handlers import show_domain_linking_intro as _handler
    return await _handler(user, message, user_lang)


async def handle_domain_linking_callback(query, callback_data: str, context, user_lang: str):
    """Handle domain linking callback"""
    from handlers import handle_domain_linking_callback as _handler
    return await _handler(query, callback_data, context, user_lang)


async def start_domain_linking_flow(query, context, user_lang: str):
    """Start domain linking flow"""
    from handlers import start_domain_linking_flow as _handler
    return await _handler(query, context, user_lang)


async def show_domain_linking_help(query, user_lang: str):
    """Show domain linking help"""
    from handlers import show_domain_linking_help as _handler
    return await _handler(query, user_lang)


async def handle_domain_linking_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle domain linking text input"""
    from handlers import handle_domain_linking_text_input as _handler
    return await _handler(update, context)


async def initiate_domain_linking_process(user, message, domain_name: str, context, user_lang: str):
    """Initiate domain linking process"""
    from handlers import initiate_domain_linking_process as _handler
    return await _handler(user, message, domain_name, context, user_lang)


# ============================================================================
# Domain Analysis
# ============================================================================

async def analyze_domain_status(domain_name: str) -> Dict:
    """Analyze domain status"""
    from handlers import analyze_domain_status as _handler
    return await _handler(domain_name)


async def smart_domain_handler(query, context, plan_id: str):
    """Smart domain handler for hosting flow"""
    from handlers import smart_domain_handler as _handler
    return await _handler(query, context, plan_id)


# ============================================================================
# Helper Functions
# ============================================================================

def is_valid_domain_format(domain: str) -> bool:
    """Check if domain format is valid"""
    from handlers import is_valid_domain_format as _func
    return _func(domain)


def get_domain_validation_error(domain_name: str, user_lang: str = None) -> str:
    """Get domain validation error message"""
    from handlers import get_domain_validation_error as _func
    return _func(domain_name, user_lang)
