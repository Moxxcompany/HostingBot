"""
Payment Handlers - Wallet and payment processing

Contains actual implementations for:
- Wallet interface display
- Wallet deposits
- Crypto payment processing
- Payment status checking
"""

import logging
from typing import Optional, Dict, List, Any
from decimal import Decimal
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.common import (
    safe_edit_message,
    escape_html,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Imports helper
# ============================================================================

def _get_imports():
    """Lazy imports to avoid circular dependencies"""
    from localization import t, t_for_user
    from database import get_or_create_user, get_user_wallet_balance, get_user_wallet_transactions
    from brand_config import BrandConfig
    from currency_utils import format_money
    return t, t_for_user, get_or_create_user, get_user_wallet_balance, get_user_wallet_transactions, BrandConfig, format_money


async def get_user_lang_fast(user, context):
    """Get user language with caching"""
    from handlers.common import get_user_lang_fast as _get_user_lang_fast
    return await _get_user_lang_fast(user, context)


# ============================================================================
# Wallet Interface (Implemented)
# ============================================================================

async def show_wallet_interface(query, context=None):
    """Show wallet interface with real balance and recent transactions"""
    t, t_for_user, get_or_create_user, get_user_wallet_balance, get_user_wallet_transactions, BrandConfig, format_money = _get_imports()
    
    # Clear admin states when navigating to wallet
    try:
        from admin_handlers import clear_admin_states
        if context:
            clear_admin_states(context)
    except ImportError:
        pass
    
    user = query.from_user
    user_lang = await get_user_lang_fast(user, context)
    
    try:
        user_record = await get_or_create_user(user.id)
        balance = await get_user_wallet_balance(user.id)
        
        # Get recent transactions
        transactions = await get_user_wallet_transactions(user_record['id'], 5)
        
        # Format transaction history
        transaction_history = ""
        if transactions:
            for tx in transactions[:3]:  # Only show 3 recent
                amount = float(tx['amount'])
                date = tx['created_at'].strftime('%m/%d')
                emoji = "➕" if amount > 0 else "➖"
                tx_type = tx['transaction_type'] or 'transaction'
                
                # Extract simple type from verbose descriptions
                if 'domain' in tx_type.lower():
                    simple_type = t('wallet.transaction_type.domain', user_lang)
                elif 'deposit' in tx_type.lower() or 'crypto' in tx_type.lower():
                    simple_type = t('wallet.transaction_type.deposit', user_lang)
                elif 'credit' in tx_type.lower():
                    simple_type = t('wallet.transaction_type.credit', user_lang)
                elif 'refund' in tx_type.lower():
                    simple_type = t('wallet.transaction_type.refund', user_lang)
                elif 'debit' in tx_type.lower():
                    simple_type = t('wallet.transaction_type.debit', user_lang)
                else:
                    simple_type = t('wallet.transaction_type.transaction', user_lang)
                
                transaction_history += f"{emoji} {format_money(abs(Decimal(str(amount))), 'USD', include_currency=True)} - {simple_type} ({date})\n"
        else:
            transaction_history = f"\n{t('wallet.no_transactions', user_lang)}"
        
        # Get brand config for dynamic support contact
        config = BrandConfig()
        
        message = f"""
{t('wallet.title', user_lang)}

{t('wallet.balance_label', user_lang)} {format_money(balance, 'USD', include_currency=True)}
{transaction_history}

{t('wallet.help_message', user_lang, support_contact=config.support_contact)}"""
        
        keyboard = [
            [InlineKeyboardButton(t("buttons.add_funds", user_lang), callback_data="wallet_deposit")],
            [InlineKeyboardButton(t("buttons.transaction_history", user_lang), callback_data="wallet_history")],
            [InlineKeyboardButton(t("buttons.back", user_lang), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await safe_edit_message(query, message, reply_markup=reply_markup)
        
    except Exception as e:
        logger.error("Error showing wallet interface: %s", e)
        user_lang = await get_user_lang_fast(query.from_user, context)
        await safe_edit_message(query, t('errors.wallet_load_failed', user_lang))


async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /wallet command - show wallet as new message"""
    t, _, get_or_create_user, get_user_wallet_balance, _, BrandConfig, format_money = _get_imports()
    
    user = update.effective_user
    user_lang = await get_user_lang_fast(user, context)
    
    try:
        balance = await get_user_wallet_balance(user.id)
        config = BrandConfig()
        
        message = f"""
{t('wallet.title', user_lang)}

{t('wallet.balance_label', user_lang)} {format_money(balance, 'USD', include_currency=True)}

{t('wallet.help_message', user_lang, support_contact=config.support_contact)}"""
        
        keyboard = [
            [InlineKeyboardButton(t("buttons.add_funds", user_lang), callback_data="wallet_deposit")],
            [InlineKeyboardButton(t("buttons.transaction_history", user_lang), callback_data="wallet_history")],
            [InlineKeyboardButton(t("buttons.back", user_lang), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error("Error in wallet command: %s", e)
        await update.message.reply_text(t('errors.wallet_load_failed', user_lang))


async def show_wallet_interface_message(update: Update):
    """Show wallet interface as a new message (not edit)"""
    from handlers_main import show_wallet_interface_message as _handler
    return await _handler(update)


async def show_wallet_balance(query, context):
    """Show wallet balance only"""
    t, _, _, get_user_wallet_balance, _, _, format_money = _get_imports()
    
    user = query.from_user
    user_lang = await get_user_lang_fast(user, context)
    
    try:
        balance = await get_user_wallet_balance(user.id)
        
        message = f"""
💰 {t('wallet.balance_title', user_lang)}

{t('wallet.balance_label', user_lang)} {format_money(balance, 'USD', include_currency=True)}
"""
        
        keyboard = [
            [InlineKeyboardButton(t("buttons.back", user_lang), callback_data="wallet_view")]
        ]
        
        await safe_edit_message(query, message, reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        logger.error("Error showing wallet balance: %s", e)


async def show_wallet_transactions(query, context):
    """Show wallet transaction history"""
    t, _, get_or_create_user, _, get_user_wallet_transactions, _, format_money = _get_imports()
    
    user = query.from_user
    user_lang = await get_user_lang_fast(user, context)
    
    try:
        user_record = await get_or_create_user(user.id)
        transactions = await get_user_wallet_transactions(user_record['id'], 10)
        
        if not transactions:
            message = f"📜 {t('wallet.history_title', user_lang)}\n\n{t('wallet.no_transactions', user_lang)}"
        else:
            message = f"📜 {t('wallet.history_title', user_lang)}\n\n"
            
            for tx in transactions:
                amount = float(tx['amount'])
                date = tx['created_at'].strftime('%Y-%m-%d %H:%M')
                emoji = "➕" if amount > 0 else "➖"
                tx_type = tx['transaction_type'] or 'Transaction'
                
                message += f"{emoji} {format_money(abs(Decimal(str(amount))), 'USD', include_currency=True)}\n"
                message += f"   {tx_type}\n"
                message += f"   {date}\n\n"
        
        keyboard = [
            [InlineKeyboardButton(t("buttons.back", user_lang), callback_data="wallet_view")]
        ]
        
        await safe_edit_message(query, message, reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        logger.error("Error showing wallet transactions: %s", e)


# ============================================================================
# Wallet Deposits (Delegated)
# ============================================================================

async def credit_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /credit command"""
    from handlers_main import credit_wallet_command as _handler
    return await _handler(update, context)


async def show_wallet_deposit_options(query, context):
    """Show wallet deposit options"""
    from handlers_main import show_wallet_deposit_options as _handler
    return await _handler(query, context)


async def show_wallet_deposit_amount(query, crypto_type: str, context):
    """Show deposit amount selection"""
    from handlers_main import show_wallet_deposit_amount as _handler
    return await _handler(query, crypto_type, context)


async def process_wallet_deposit(query, crypto_type: str, amount: str, context):
    """Process wallet deposit"""
    from handlers_main import process_wallet_deposit as _handler
    return await _handler(query, crypto_type, amount, context)


# ============================================================================
# Crypto Payments (Delegated)
# ============================================================================

async def show_crypto_payment_qr(query, payment_address: str, amount: float, crypto_type: str):
    """Show crypto payment QR code"""
    from handlers_main import show_crypto_payment_qr as _handler
    return await _handler(query, payment_address, amount, crypto_type)


async def check_crypto_payment_status(query, payment_id: str, context):
    """Check crypto payment status"""
    from handlers_main import check_crypto_payment_status as _handler
    return await _handler(query, payment_id, context)


async def handle_crypto_currency_selection(query, context, service_type: str, service_id: str):
    """Handle crypto currency selection"""
    from handlers_main import handle_crypto_currency_selection as _handler
    return await _handler(query, context, service_type, service_id)


# ============================================================================
# Payment Processing (Delegated)
# ============================================================================

async def process_wallet_payment(query, amount: float, description: str, context):
    """Process wallet payment"""
    from handlers_main import process_wallet_payment as _handler
    return await _handler(query, amount, description, context)


async def show_payment_success(query, amount: float, service: str, context):
    """Show payment success message"""
    from handlers_main import show_payment_success as _handler
    return await _handler(query, amount, service, context)


async def show_payment_failed(query, reason: str, context):
    """Show payment failed message"""
    from handlers_main import show_payment_failed as _handler
    return await _handler(query, reason, context)


# ============================================================================
# Hosting Payment Options (Delegated)
# ============================================================================

async def show_hosting_payment_options(query, subscription_id: int, price: float, plan_name: str, domain_name: str):
    """Show hosting payment options"""
    from handlers_main import show_hosting_payment_options as _handler
    return await _handler(query, subscription_id, price, plan_name, domain_name)


async def show_hosting_payment_options_with_intent(query, intent_id: int, price: float, plan_name: str, domain_name: str):
    """Show hosting payment options with intent"""
    from handlers_main import show_hosting_payment_options_with_intent as _handler
    return await _handler(query, intent_id, price, plan_name, domain_name)


async def process_hosting_crypto_payment(query, crypto_type: str, subscription_id: str, price: str):
    """Process hosting crypto payment"""
    from handlers_main import process_hosting_crypto_payment as _handler
    return await _handler(query, crypto_type, subscription_id, price)


async def process_hosting_wallet_payment(query, subscription_id: str, price: str):
    """Process hosting wallet payment"""
    from handlers_main import process_hosting_wallet_payment as _handler
    return await _handler(query, subscription_id, price)


# ============================================================================
# Unified Payment Options (Delegated)
# ============================================================================

async def show_unified_payment_options(query, subscription_id: int, price: float, plan_name: str, domain_name: str, items: List[str], service_type: str):
    """Show unified payment options"""
    from handlers_main import show_unified_payment_options as _handler
    return await _handler(query, subscription_id, price, plan_name, domain_name, items, service_type)
