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
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.common import (
    safe_edit_message,
    escape_html,
    get_user_lang_fast,
)
from database import (
    get_or_create_user, get_hosting_subscription_details, get_user_wallet_balance,
)
from localization import t, t_html, resolve_user_language, btn_t
from services.cpanel import CPanelService

logger = logging.getLogger(__name__)

# Initialize services
cpanel = CPanelService()


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
    """Show individual hosting account management interface"""
    user = query.from_user
    
    try:
        # Get user language early for translations
        user_lang = await resolve_user_language(user.id, user.language_code if hasattr(user, "language_code") else None)
        
        # Get user from database
        db_user = await get_or_create_user(telegram_id=user.id)
        
        # Get hosting subscription details
        subscription = await get_hosting_subscription_details(int(subscription_id), db_user['id'])
        
        if not subscription:
            await safe_edit_message(query, t("hosting.not_found_or_denied", user_lang))
            return
        
        domain_name = subscription.get('domain_name') or t("common_labels.unknown", user_lang)
        plan_name = subscription.get('plan_name') or t("common_labels.unknown", user_lang)
        status = subscription.get('status', 'unknown')
        cpanel_username = subscription.get('cpanel_username') or t("common_labels.not_assigned", user_lang)
        created_date = subscription.get('created_at', '')
        
        # Format creation date
        if created_date:
            try:
                if isinstance(created_date, str):
                    created_date = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                formatted_date = created_date.strftime('%B %d, %Y')
            except:
                formatted_date = str(created_date)[:10]
        else:
            formatted_date = t("common_labels.unknown", user_lang)
        
        # Status indicator and available actions
        if status == 'active':
            status_icon = "🟢"
            status_text = t("common_labels.active", user_lang)
            action_buttons = [
                [InlineKeyboardButton(btn_t('suspend_account', user_lang), callback_data=f"suspend_hosting_{subscription_id}")],
                [InlineKeyboardButton(btn_t('restart_services', user_lang), callback_data=f"restart_hosting_{subscription_id}")]
            ]
        elif status == 'suspended':
            status_icon = "🔴"
            status_text = t("common_labels.suspended", user_lang)
            
            # Show days until deletion if deletion is scheduled
            deletion_scheduled = subscription.get('deletion_scheduled_for')
            days_until_deletion = "?"
            if deletion_scheduled:
                days_left = (deletion_scheduled - datetime.now(timezone.utc)).days
                days_until_deletion = max(0, days_left)
            
            action_buttons = [
                [InlineKeyboardButton(btn_t("renew_hosting", user_lang, days=days_until_deletion), callback_data=f"renew_suspended_{subscription_id}")]
            ]
        elif status == 'pending':
            status_icon = "🟡"
            status_text = t("common_labels.pending_setup", user_lang)
            action_buttons = []
        else:
            status_icon = "⚪"
            status_text = t(f"common_labels.{status.lower()}", user_lang) if status and status.lower() in ["active", "suspended", "pending", "expired", "failed"] else t("common_labels.unknown", user_lang)
            action_buttons = []
        
        message = f"""
🏠 <b>{t("hosting.management_title", user_lang)}</b>

<b>{t("common_labels.domain", user_lang)}</b> <code>{domain_name}</code>
<b>{t("common_labels.plan", user_lang)}</b> {plan_name}
<b>{t("common_labels.status", user_lang)}</b> {status_icon} {status_text}
<b>{t("hosting.cpanel_username_label", user_lang)}</b> <code>{cpanel_username}</code>
<b>{t("common_labels.created", user_lang)}</b> {formatted_date}

{get_hosting_status_description(status, user_lang)}
"""
        
        keyboard = []
        
        # Add management actions
        keyboard.extend(action_buttons)
        
        # Add information buttons
        keyboard.extend([
            [InlineKeyboardButton(btn_t('account_details', user_lang), callback_data=f"hosting_details_{subscription_id}")],
            [InlineKeyboardButton(btn_t('cpanel_login', user_lang), callback_data=f"cpanel_login_{subscription_id}")],
            [InlineKeyboardButton(btn_t('usage_stats', user_lang), callback_data=f"hosting_usage_{subscription_id}")]
        ])
        
        # Navigation
        keyboard.extend([
            [InlineKeyboardButton(btn_t('back_to_my_hosting', user_lang), callback_data="my_hosting")],
            [InlineKeyboardButton(btn_t('main_menu', user_lang), callback_data="main_menu")]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(query, message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error showing hosting management: {e}")
        user_lang = await resolve_user_language(user.id, user.language_code if hasattr(user, "language_code") else None)
        await safe_edit_message(query, t("errors.generic_try_again", user_lang))


async def show_hosting_details(query, subscription_id: str):
    """Show detailed hosting account information"""
    user = query.from_user
    
    try:
        # Get user language early for translations
        user_lang = await resolve_user_language(user.id, user.language_code if hasattr(user, "language_code") else None)
        
        # Get user from database
        db_user = await get_or_create_user(telegram_id=user.id)
        
        # Get hosting subscription details
        subscription = await get_hosting_subscription_details(int(subscription_id), db_user['id'])
        
        if not subscription:
            await safe_edit_message(query, t("hosting.not_found_or_denied", user_lang))
            return
        
        domain_name = subscription.get('domain_name') or t("common_labels.not_assigned", user_lang)
        plan_name = subscription.get('plan_name') or t("common_labels.unknown", user_lang)
        status = subscription.get('status', 'unknown')
        server_ip = subscription.get('server_ip') or t("common_labels.not_assigned", user_lang)
        created_at = subscription.get('created_at')
        next_billing = subscription.get('next_billing_date')
        
        # Format dates
        formatted_created = created_at.strftime("%B %d, %Y") if created_at else t("common_labels.unknown", user_lang)
        formatted_billing = next_billing.strftime("%B %d, %Y") if next_billing else t("common_labels.unknown", user_lang)
        
        # Format status text
        if status and status.lower() in ["active", "suspended", "pending", "pending_setup", "expired", "failed"]:
            status_display = t(f"common_labels.{status.lower()}", user_lang)
        else:
            status_display = t("common_labels.unknown", user_lang)
        
        message = f"""
📊 <b>{t("hosting.account_details_title", user_lang)}</b>

<b>{t("common_labels.domain", user_lang)}</b> <code>{domain_name}</code>
<b>{t("common_labels.plan", user_lang)}</b> {plan_name}
<b>{t("common_labels.server_ip", user_lang)}</b> <code>{server_ip}</code>
<b>{t("common_labels.status", user_lang)}</b> {status_display}
<b>{t("common_labels.created", user_lang)}</b> {formatted_created}
<b>{t("common_labels.next_billing", user_lang)}</b> {formatted_billing}

💡 {t("hosting.account_details_info", user_lang)}
"""
        
        keyboard = [
            [InlineKeyboardButton(btn_t('back_to_management', user_lang), callback_data=f"manage_hosting_{subscription_id}")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(query, message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error showing hosting details: {e}")
        user_lang = await resolve_user_language(user.id, user.language_code if hasattr(user, "language_code") else None)
        await safe_edit_message(query, t("errors.generic_try_again", user_lang))


async def show_cpanel_login(query, subscription_id: str):
    """Show cPanel login credentials with copy functionality"""
    user = query.from_user
    
    try:
        # Get user language early for translations
        user_lang = await resolve_user_language(user.id, user.language_code if hasattr(user, "language_code") else None)
        
        # Get user from database
        db_user = await get_or_create_user(telegram_id=user.id)
        
        # Get hosting subscription details
        subscription = await get_hosting_subscription_details(int(subscription_id), db_user['id'])
        
        if not subscription:
            await safe_edit_message(query, t("hosting.not_found_or_denied", user_lang))
            return
        
        not_assigned = t("common_labels.not_assigned", user_lang)
        domain_name = subscription.get('domain_name', 'hostingbay.sbs')
        cpanel_username = subscription.get('cpanel_username') or not_assigned
        cpanel_password = subscription.get('cpanel_password') or not_assigned
        server_ip = subscription.get('server_ip') or not_assigned
        
        # Construct cPanel URL
        cpanel_url = f"https://{domain_name}:2083" if domain_name != not_assigned else f"https://{server_ip}:2083"
        
        message = f"""
🔧 <b>{t("hosting.cpanel_login_title", user_lang)}</b>

<b>🌐 {t("common_labels.url", user_lang)}</b> <code>{cpanel_url}</code>
<b>👤 {t("common_labels.username", user_lang)}</b> <code>{cpanel_username}</code>
<b>🔑 {t("common_labels.password", user_lang)}</b> <code>{cpanel_password}</code>
<b>🖥️ {t("common_labels.server", user_lang)}</b> <code>{server_ip}</code>

💡 {t("hosting.tap_to_copy", user_lang)}
💾 {t("hosting.save_credentials", user_lang)}
"""
        
        keyboard = [
            [InlineKeyboardButton(btn_t('back_to_management', user_lang), callback_data=f"manage_hosting_{subscription_id}")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(query, message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error showing cPanel login: {e}")
        user_lang = await resolve_user_language(user.id, user.language_code if hasattr(user, "language_code") else None)
        await safe_edit_message(query, t("errors.generic_try_again", user_lang))


async def show_hosting_usage(query, subscription_id: str):
    """Show hosting usage statistics"""
    user = query.from_user
    
    try:
        # Get user language early for translations
        user_lang = await resolve_user_language(user.id, user.language_code if hasattr(user, "language_code") else None)
        
        # Get user from database
        db_user = await get_or_create_user(telegram_id=user.id)
        
        # Get hosting subscription details
        subscription = await get_hosting_subscription_details(int(subscription_id), db_user['id'])
        
        if not subscription:
            await safe_edit_message(query, t("hosting.not_found_or_denied", user_lang))
            return
        
        domain_name = subscription.get('domain_name') or t("common_labels.not_assigned", user_lang)
        plan_name = subscription.get('plan_name') or t("common_labels.unknown", user_lang)
        unlimited_text = t("hosting.unlimited", user_lang)
        
        # For now, show placeholder usage stats (can be enhanced with real cPanel API integration)
        message = f"""
📈 <b>{t("hosting.usage_statistics_title", user_lang)}</b>

<b>{t("common_labels.domain", user_lang)}</b> <code>{domain_name}</code>
<b>{t("common_labels.plan", user_lang)}</b> {plan_name}

<b>📦 {t("hosting.disk_usage_label", user_lang)}</b> 0.1 GB / 5.0 GB (2%)
<b>📊 {t("hosting.bandwidth_label", user_lang)}</b> 0.5 GB / 50 GB (1%)
<b>📁 {t("hosting.files_label", user_lang)}</b> 12 / {unlimited_text}
<b>📧 {t("hosting.email_accounts_label", user_lang)}</b> 1 / {unlimited_text}
<b>🗂️ {t("hosting.databases_label", user_lang)}</b> 0 / 10

<b>⏱️ {t("hosting.uptime_label", user_lang)}</b> 99.9%
<b>🔄 {t("hosting.last_updated_label", user_lang)}</b> {t("hosting.just_now", user_lang)}

💡 {t("hosting.usage_update_hourly", user_lang)}
"""
        
        keyboard = [
            [InlineKeyboardButton(btn_t('back_to_management', user_lang), callback_data=f"manage_hosting_{subscription_id}")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(query, message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error showing hosting usage: {e}")
        user_lang = await resolve_user_language(user.id, user.language_code if hasattr(user, "language_code") else None)
        await safe_edit_message(query, t("errors.generic_try_again", user_lang))


# ============================================================================
# Hosting Lifecycle Management
# ============================================================================

async def handle_renew_suspended_hosting(query, subscription_id: str):
    """Show payment options for manually renewing suspended hosting account"""
    user = query.from_user
    
    try:
        from database import get_hosting_plan
        
        # Get user from database
        db_user = await get_or_create_user(telegram_id=user.id)
        
        # Get hosting subscription details
        subscription = await get_hosting_subscription_details(int(subscription_id), db_user['id'])
        
        # Get user language early for translations
        user_lang = await resolve_user_language(user.id, user.language_code if hasattr(user, "language_code") else None)
        
        if not subscription:
            await safe_edit_message(query, f"❌ {t('hosting.not_found_or_denied', user_lang)}")
            return
        
        if subscription['status'] != 'suspended':
            await safe_edit_message(query, f"⚠️ This account is not suspended.")
            return
        
        domain_name = subscription.get('domain_name', 'unknown')
        plan_name = subscription.get('plan_name') or t("common_labels.unknown", user_lang)
        
        # Calculate renewal cost based on plan
        plan_id = subscription.get('plan_id')
        if not plan_id:
            await safe_edit_message(query, f"❌ {t('hosting.invalid_plan_contact_support', user_lang)}")
            return
        plan = await get_hosting_plan(int(plan_id))
        renewal_cost = plan['monthly_price'] if plan else 0.0
        
        # Get current wallet balance (use telegram_id, not internal user_id)
        wallet_balance = await get_user_wallet_balance(user.id)
        
        # Create message
        message = f"""
💳 <b>{t("renewal.title", user_lang)}</b>

<b>{t("common_labels.domain", user_lang)}</b> <code>{domain_name}</code>
<b>{t("common_labels.plan", user_lang)}</b> {plan_name}
<b>{t("renewal.renewal_cost", user_lang)}</b> ${renewal_cost:.2f}

<b>{t("renewal.your_wallet_balance", user_lang)}</b> ${float(wallet_balance):.2f}

{t("renewal.choose_payment_method", user_lang)}
"""
        
        # Create payment buttons
        keyboard = []
        
        # Wallet payment button (with balance check)
        if wallet_balance >= renewal_cost:
            keyboard.append([InlineKeyboardButton(
                f"💰 {t('renewal.pay_from_wallet', user_lang)} (${float(wallet_balance):.2f})",
                callback_data=f"renew_wallet_{subscription_id}"
            )])
        else:
            # Show insufficient funds with add funds option
            keyboard.append([InlineKeyboardButton(
                f"💰 {t('renewal.wallet_insufficient', user_lang)} (${float(wallet_balance):.2f} / ${renewal_cost:.2f})",
                callback_data=f"insufficient_funds_{subscription_id}"
            )])
        
        # Crypto payment button
        keyboard.append([InlineKeyboardButton(
            f"₿ {t('payment.hosting.crypto_button', user_lang)}",
            callback_data=f"renew_crypto_{subscription_id}"
        )])
        
        # Back button
        keyboard.append([InlineKeyboardButton(
            t("buttons.back_to_management", user_lang),
            callback_data=f"manage_hosting_{subscription_id}"
        )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(query, message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error showing renewal options: {e}")
        user_lang = await resolve_user_language(user.id, user.language_code if hasattr(user, "language_code") else None)
        await safe_edit_message(query, f"❌ {t('errors.general', user_lang)}")


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
    """Show confirmation for hosting account suspension"""
    user = query.from_user
    
    try:
        # Get user language early for translations
        user_lang = await resolve_user_language(user.id, user.language_code if hasattr(user, "language_code") else None)
        
        # Get user from database
        db_user = await get_or_create_user(telegram_id=user.id)
        
        # Get hosting subscription details
        subscription = await get_hosting_subscription_details(int(subscription_id), db_user['id'])
        
        if not subscription:
            await safe_edit_message(query, t("hosting.not_found_or_denied", user_lang))
            return
        
        domain_name = subscription.get('domain_name') or t("common_labels.unknown", user_lang)
        plan_name = subscription.get('plan_name') or t("common_labels.unknown", user_lang)
        
        message = f"""
⚠️ <b>{t("hosting.suspend_title", user_lang)}</b>

<b>{t("common_labels.domain", user_lang)}</b> <code>{domain_name}</code>
<b>{t("common_labels.plan", user_lang)}</b> {plan_name}

<b>⚠️ {t("hosting.warning_label", user_lang)}</b> {t("hosting.suspend_warning_intro", user_lang)}:
• {t("hosting.suspend_warning_1", user_lang)}
• {t("hosting.suspend_warning_2", user_lang)}
• {t("hosting.suspend_warning_3", user_lang)}
• {t("hosting.suspend_warning_4", user_lang)}

{t("hosting.suspend_preservation", user_lang)}

{t("hosting.suspend_confirmation", user_lang)}
"""
        
        keyboard = [
            [InlineKeyboardButton(btn_t('yes_suspend', user_lang), callback_data=f"confirm_suspend_{subscription_id}")],
            [InlineKeyboardButton(btn_t('cancel', user_lang), callback_data=f"cancel_suspend_{subscription_id}")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(query, message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error showing suspension confirmation: {e}")
        user_lang = await resolve_user_language(user.id, user.language_code if hasattr(user, "language_code") else None)
        await safe_edit_message(query, t("errors.generic_try_again", user_lang))


async def confirm_hosting_suspension(query, subscription_id: str):
    """Execute hosting account suspension"""
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
    """Get description for hosting status"""
    descriptions = {
        'active': t("hosting.status_desc_active", user_lang),
        'suspended': t("hosting.status_desc_suspended", user_lang),
        'pending': t("hosting.status_desc_pending", user_lang),
        'expired': t("hosting.status_desc_expired", user_lang),
        'cancelled': t("hosting.status_desc_cancelled", user_lang)
    }
    return descriptions.get(status, t("hosting.status_desc_unavailable", user_lang))


async def show_insufficient_funds_message(query, subscription_id: str):
    """Show insufficient funds message"""
    from handlers_main import show_insufficient_funds_message as _handler
    return await _handler(query, subscription_id)
