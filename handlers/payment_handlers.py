"""
Payment Handlers - Wallet and payment processing

Handles:
- Wallet display and management
- Wallet deposits
- Crypto payment processing
- Payment status checking
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
# Wallet Interface
# ============================================================================

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /wallet command"""
    from handlers import wallet_command as _handler
    return await _handler(update, context)


async def show_wallet_interface(query, context=None):
    """Show wallet interface"""
    from handlers import show_wallet_interface as _handler
    return await _handler(query, context)


async def show_wallet_interface_message(update: Update):
    """Show wallet interface as message"""
    from handlers import show_wallet_interface_message as _handler
    return await _handler(update)


async def show_wallet_balance(query, context):
    """Show wallet balance"""
    from handlers import show_wallet_balance as _handler
    return await _handler(query, context)


async def show_wallet_transactions(query, context):
    """Show wallet transaction history"""
    from handlers import show_wallet_transactions as _handler
    return await _handler(query, context)


# ============================================================================
# Wallet Deposits
# ============================================================================

async def credit_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /credit command"""
    from handlers import credit_wallet_command as _handler
    return await _handler(update, context)


async def show_wallet_deposit_options(query, context):
    """Show wallet deposit options"""
    from handlers import show_wallet_deposit_options as _handler
    return await _handler(query, context)


async def show_wallet_deposit_amount(query, crypto_type: str, context):
    """Show deposit amount selection"""
    from handlers import show_wallet_deposit_amount as _handler
    return await _handler(query, crypto_type, context)


async def process_wallet_deposit(query, crypto_type: str, amount: str, context):
    """Process wallet deposit"""
    from handlers import process_wallet_deposit as _handler
    return await _handler(query, crypto_type, amount, context)


# ============================================================================
# Crypto Payments
# ============================================================================

async def show_crypto_payment_qr(query, payment_address: str, amount: float, crypto_type: str):
    """Show crypto payment QR code"""
    from handlers import show_crypto_payment_qr as _handler
    return await _handler(query, payment_address, amount, crypto_type)


async def check_crypto_payment_status(query, payment_id: str, context):
    """Check crypto payment status"""
    from handlers import check_crypto_payment_status as _handler
    return await _handler(query, payment_id, context)


async def handle_crypto_currency_selection(query, context, service_type: str, service_id: str):
    """Handle crypto currency selection"""
    from handlers import handle_crypto_currency_selection as _handler
    return await _handler(query, context, service_type, service_id)


# ============================================================================
# Payment Processing
# ============================================================================

async def process_wallet_payment(query, amount: float, description: str, context):
    """Process wallet payment"""
    from handlers import process_wallet_payment as _handler
    return await _handler(query, amount, description, context)


async def show_payment_success(query, amount: float, service: str, context):
    """Show payment success message"""
    from handlers import show_payment_success as _handler
    return await _handler(query, amount, service, context)


async def show_payment_failed(query, reason: str, context):
    """Show payment failed message"""
    from handlers import show_payment_failed as _handler
    return await _handler(query, reason, context)


# ============================================================================
# Hosting Payment Options
# ============================================================================

async def show_hosting_payment_options(query, subscription_id: int, price: float, plan_name: str, domain_name: str):
    """Show hosting payment options"""
    from handlers import show_hosting_payment_options as _handler
    return await _handler(query, subscription_id, price, plan_name, domain_name)


async def show_hosting_payment_options_with_intent(query, intent_id: int, price: float, plan_name: str, domain_name: str):
    """Show hosting payment options with intent"""
    from handlers import show_hosting_payment_options_with_intent as _handler
    return await _handler(query, intent_id, price, plan_name, domain_name)


async def process_hosting_crypto_payment(query, crypto_type: str, subscription_id: str, price: str):
    """Process hosting crypto payment"""
    from handlers import process_hosting_crypto_payment as _handler
    return await _handler(query, crypto_type, subscription_id, price)


async def process_hosting_wallet_payment(query, subscription_id: str, price: str):
    """Process hosting wallet payment"""
    from handlers import process_hosting_wallet_payment as _handler
    return await _handler(query, subscription_id, price)


# ============================================================================
# Unified Payment Options
# ============================================================================

async def show_unified_payment_options(query, subscription_id: int, price: float, plan_name: str, domain_name: str, items: List[str], service_type: str):
    """Show unified payment options"""
    from handlers import show_unified_payment_options as _handler
    return await _handler(query, subscription_id, price, plan_name, domain_name, items, service_type)
