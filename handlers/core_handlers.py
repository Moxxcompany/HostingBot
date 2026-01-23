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
import asyncio
import time
from decimal import Decimal
from typing import Optional, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.common import (
    safe_edit_message,
    get_user_lang_fast,
    decompress_callback,
    clear_all_dns_wizard_state,
    escape_html,
)
from database import (
    get_or_create_user, execute_query, get_user_wallet_balance,
    accept_user_terms, has_user_accepted_terms, get_or_create_user_with_status,
)
from brand_config import (
    get_welcome_message, get_platform_name, BrandConfig,
    format_branded_message, get_support_contact
)
from admin_handlers import is_admin_user, clear_admin_states
from pricing_utils import format_money
from message_utils import t_fmt, create_contact_support_message
from localization import (
    t, t_for_user, resolve_user_language, t_html, t_html_for_user,
    set_user_language_preference, get_supported_languages, is_language_supported,
    get_user_language_preference, btn_t
)
from utils.user_context import get_user_language_cached

logger = logging.getLogger(__name__)


# ============================================================================
# User Onboarding Check
# ============================================================================

async def require_user_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Check if user has completed onboarding (terms acceptance).
    Returns True if user is authenticated, False if they need to complete /start.
    """
    user = update.effective_user
    effective_message = update.effective_message
    
    if not user or not effective_message:
        logger.error("Missing user or message in authentication check")
        return False
    
    try:
        # Get user data from database
        user_data = await get_or_create_user_with_status(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        # Check if user has accepted terms
        if not user_data['terms_accepted_bool']:
            # User hasn't completed onboarding - direct them to /start
            user_lang = await get_user_lang_fast(user, context)
            
            onboarding_message = t('auth.onboarding_required', user_lang)
            
            keyboard = [
                [InlineKeyboardButton(t("buttons.start_onboarding", user_lang), url=f"https://t.me/{context.bot.username}?start=onboard")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await effective_message.reply_text(
                onboarding_message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            
            logger.warning(f"🚫 SECURITY: User {user.id} (@{user.username or 'no_username'}) attempted to access command without completing onboarding")
            return False
        
        # User is authenticated
        return True
        
    except Exception as e:
        logger.error(f"Error in authentication check for user {user.id}: {e}")
        
        # Get user_lang for error message
        user_lang = await get_user_lang_fast(user, context)
        
        # Fallback error message
        await effective_message.reply_text(
            t('auth.error', user_lang),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(t("buttons.start_bot", user_lang), url=f"https://t.me/{context.bot.username}?start=auth")
            ]])
        )
        return False


# ============================================================================
# Main Commands
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with terms acceptance check and routing"""
    user = update.effective_user
    message = update.effective_message
    
    if not user or not message:
        logger.error("Missing user or message in start command")
        return
    
    # MAINTENANCE MODE CHECK - Block non-admin users during maintenance
    from services.maintenance_manager import MaintenanceManager
    is_active = await MaintenanceManager.is_maintenance_active()
    if is_active and not is_admin_user(user.id):
        user_lang = await get_user_language_cached(update, context)
        maintenance_message = await MaintenanceManager.get_maintenance_message(user_lang)
        await message.reply_text(maintenance_message, parse_mode=ParseMode.HTML)
        logger.info(f"🔧 MAINTENANCE: Blocked /start command from non-admin user {user.id}")
        return
    
    try:
        # Clear admin states when user starts fresh
        clear_admin_states(context)
        
        # Clear all DNS wizard state to ensure fresh start
        clear_all_dns_wizard_state(context)
        
        # USER INTERACTION LOG: Enhanced logging for anomaly detection
        logger.info(f"🚀 USER_ACTIVITY: /start command from user {user.id} (@{user.username or 'no_username'}) '{user.first_name or 'Unknown'}'")
        
        # PERFORMANCE OPTIMIZATION: Single query for all user data
        user_data = await get_or_create_user_with_status(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        # LANGUAGE SELECTION LOGIC: Show to users who haven't manually selected language
        # Check if user has manually selected a language
        lang_result = await execute_query(
            "SELECT preferred_language, language_selected_manually FROM users WHERE telegram_id = %s",
            (user.id,)
        )
        
        if lang_result:
            stored_language = lang_result[0]['preferred_language']
            manually_selected = lang_result[0]['language_selected_manually']
            # Normalize empty string to None
            if stored_language == '':
                stored_language = None
        else:
            stored_language = None
            manually_selected = False
        
        # CRITICAL FIX: Only show language selection for truly new users or users who haven't accepted terms
        # Existing users who already accepted terms should not be forced through language selection
        terms_accepted = user_data['terms_accepted_bool']
        
        # Show language selection if:
        # 1. User is newly created AND hasn't accepted terms yet (true new users)
        # 2. User hasn't accepted terms yet AND has no language preference (incomplete onboarding)
        should_show_language_selection = (
            not terms_accepted and (
                stored_language is None or  # Never selected language
                user_data.get('created_recently', False) or  # Newly created user
                not manually_selected  # Never manually selected (for users in onboarding)
            )
        )
        
        if should_show_language_selection:
            logger.info(f"🌍 User {user.id} needs language selection (stored: {stored_language}, manually_selected: {manually_selected}, new: {user_data.get('created_recently', False)})")
            language_selected = await show_language_selection(update, context)
            if language_selected:
                return  # Wait for user to select language
            else:
                # Robust fallback to English if language selection fails
                logger.warning(f"Language selection failed for user {user.id}, using English fallback")
                await set_user_language_preference(user.id, 'en', manually_selected=False)
        elif terms_accepted and stored_language is None:
            # EXISTING USER FIX: Auto-assign language for existing users who accepted terms before language selection was implemented
            from localization import detect_user_language
            auto_language = detect_user_language(user.language_code)
            await set_user_language_preference(user.id, auto_language, manually_selected=False)
            logger.info(f"🔄 Auto-assigned language '{auto_language}' to existing user {user.id} who already accepted terms")
        
        # Get current language preference after potential selection
        current_lang = await get_user_language_preference(user.id)
        
        terms_accepted = user_data['terms_accepted_bool']
        logger.info(f"🔍 TERMS CHECK: User {user.id} ({user.username}) terms_accepted = {terms_accepted}")
        
        if terms_accepted:
            # User has already accepted terms, show dashboard directly
            await show_dashboard(update, context, user_data)
            logger.info(f"✅ DASHBOARD: User {user.id} started bot - showing dashboard (terms already accepted)")
        else:
            # User has not accepted terms, show terms acceptance screen
            await show_terms_acceptance(update, context)
            logger.info(f"📋 TERMS: User {user.id} started bot - showing terms acceptance")
            
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        
        # Get user_lang for error fallback
        user_lang = await get_user_lang_fast(user, context)
        
        # Fallback to original welcome message on error
        welcome_message = get_welcome_message()
        keyboard = [
            [InlineKeyboardButton(t("buttons.search", user_lang), callback_data="search_domains"), InlineKeyboardButton(t("buttons.domains", user_lang), callback_data="my_domains")],
            [InlineKeyboardButton(t("buttons.wallet", user_lang), callback_data="wallet_main"), InlineKeyboardButton(t("buttons.hosting", user_lang), callback_data="hosting_main")],
            [InlineKeyboardButton(t("buttons.link_domain", user_lang), callback_data="domain_linking_intro"), InlineKeyboardButton(t("buttons.profile", user_lang), callback_data="profile_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await message.reply_text(welcome_message, reply_markup=reply_markup)
        except Exception as fallback_error:
            logger.error(f"Error in start command fallback: {fallback_error}")


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command to exit broadcast mode"""
    user = update.effective_user
    message = update.effective_message
    
    if not user or not message:
        logger.error("Missing user or message in cancel command")
        return
    
    try:
        # Check if user is admin using unified admin check
        if not is_admin_user(user.id):
            await message.reply_text(
                "🚫 Access Denied\n\nOnly admin can use this command."
            )
            logger.warning(f"🚫 SECURITY: Non-admin user {user.id} attempted to use /cancel command")
            return
        
        # Check if awaiting broadcast
        if context.user_data and context.user_data.get('awaiting_broadcast'):
            # Clear broadcast flag
            del context.user_data['awaiting_broadcast']
            
            await message.reply_text(
                "🚫 Broadcast Cancelled\n\nBroadcast mode deactivated.\n\nYou can start a new broadcast anytime from the admin panel."
            )
            logger.info(f"📢 ADMIN: User {user.id} cancelled broadcast mode via /cancel command")
        else:
            await message.reply_text(
                "ℹ️ No Active Operation\n\nThere is no active operation to cancel."
            )
            logger.info(f"📢 ADMIN: User {user.id} used /cancel but no active broadcast mode")
            
    except Exception as e:
        logger.error(f"Error in cancel_command: {e}")
        await message.reply_text(
            "❌ Error\n\nCould not process cancel command."
        )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /profile command with localization and community engagement"""
    user = update.effective_user
    message = update.effective_message
    
    if not user or not message:
        logger.error("Missing user or message in profile command")
        return
    
    # MAINTENANCE MODE CHECK - Block non-admin users during maintenance
    from services.maintenance_manager import MaintenanceManager
    is_active = await MaintenanceManager.is_maintenance_active()
    if is_active and not is_admin_user(user.id):
        user_lang = await get_user_lang_fast(user, context)
        maintenance_message = await MaintenanceManager.get_maintenance_message(user_lang)
        await message.reply_text(maintenance_message, parse_mode=ParseMode.HTML)
        logger.info(f"🔧 MAINTENANCE: Blocked /profile command from non-admin user {user.id}")
        return
    
    # Check if user has completed onboarding
    if not await require_user_onboarding(update, context):
        return
    
    try:
        # Get user language for localized response
        user_lang = await get_user_lang_fast(user, context)
        
        # Get user data for wallet balance and terms status
        user_data = await get_or_create_user(user.id, user.username, user.first_name, user.language_code)
        wallet_balance = await get_user_wallet_balance(user.id)
        has_accepted_terms = await has_user_accepted_terms(user.id)
        
        # Build profile information using localized strings
        username_display = f"@{user.username}" if user.username else "Not set"
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Not set"
        
        # Get brand configuration for community engagement
        config = BrandConfig()
        
        # Build profile sections
        profile_parts = []
        
        # Profile title
        title_text, _ = t_html('profile.title', user_lang)
        profile_parts.append(title_text)
        profile_parts.append("")
        
        # Telegram details section
        telegram_details, _ = t_html('profile.telegram_details', user_lang)
        profile_parts.append(telegram_details)
        
        username_text, _ = t_html('profile.username', user_lang, username=user.username or "Not set")
        profile_parts.append(username_text)
        
        name_text, _ = t_html('profile.name', user_lang, name=full_name)
        profile_parts.append(name_text)
        
        user_id_text, _ = t_html('profile.user_id', user_lang, user_id=user.id)
        profile_parts.append(user_id_text)
        profile_parts.append("")
        
        # Account status section
        account_status_text, _ = t_html('profile.account_status', user_lang)
        profile_parts.append(account_status_text)
        
        wallet_text, _ = t_html('profile.wallet_balance', user_lang, balance=format_money(wallet_balance))
        profile_parts.append(wallet_text)
        
        terms_status = "✅" if has_accepted_terms else "⏳"
        terms_text, _ = t_html('profile.terms_status', user_lang, status=terms_status)
        profile_parts.append(terms_text)
        profile_parts.append("")
        
        # Available features section
        features_text, _ = t_html('profile.features', user_lang)
        profile_parts.append(features_text)
        
        feature_domains, _ = t_html('profile.feature_domains', user_lang)
        profile_parts.append(feature_domains)
        
        feature_dns, _ = t_html('profile.feature_dns', user_lang)
        profile_parts.append(feature_dns)
        
        feature_hosting, _ = t_html('profile.feature_hosting', user_lang)
        profile_parts.append(feature_hosting)
        
        feature_crypto, _ = t_html('profile.feature_crypto', user_lang)
        profile_parts.append(feature_crypto)
        profile_parts.append("")
        
        # Community engagement section with configurable branding
        community_engagement, _ = t_html('profile.community_engagement', user_lang, 
                                        hostbay_channel=config.hostbay_channel,
                                        hostbay_email=config.hostbay_email,
                                        support_contact=config.support_contact)
        profile_parts.append(community_engagement)
        
        # Join all parts into final profile info
        profile_info = "\n".join(profile_parts)
        
        # Create keyboard with localized back button
        keyboard = [
            [InlineKeyboardButton(btn_t('back', user_lang), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text(profile_info, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        logger.info(f"✅ Profile command completed for user {user.id} in language {user_lang}")
        
    except Exception as e:
        logger.error(f"Error in profile command for user {user.id}: {e}")
        # Get user_lang for error message
        user_lang = await get_user_lang_fast(user, context)
        # Fallback error message
        error_msg = t('errors.profile_load_failed', user_lang)
        keyboard = [
            [InlineKeyboardButton(t("buttons.back", user_lang), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text(error_msg, reply_markup=reply_markup)


async def hosting_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /hosting command"""
    effective_message = update.effective_message
    if not effective_message:
        logger.error("Missing message in hosting command")
        return
    
    user = update.effective_user
    if user:
        # MAINTENANCE MODE CHECK - Block non-admin users during maintenance
        from services.maintenance_manager import MaintenanceManager
        is_active = await MaintenanceManager.is_maintenance_active()
        if is_active and not is_admin_user(user.id):
            user_lang = await get_user_lang_fast(user, context)
            maintenance_message = await MaintenanceManager.get_maintenance_message(user_lang)
            await effective_message.reply_text(maintenance_message, parse_mode=ParseMode.HTML)
            logger.info(f"🔧 MAINTENANCE: Blocked /hosting command from non-admin user {user.id}")
            return
    
    # Check if user has completed onboarding
    if not await require_user_onboarding(update, context):
        return
    
    # Get user language for localized buttons
    user_lang = await get_user_lang_fast(user, context) if user else 'en'
        
    message_text = """
🏠 Hosting

Choose a plan:
"""
    keyboard = [
        [InlineKeyboardButton(t("buttons.plans", user_lang), callback_data="hosting_plans")],
        [InlineKeyboardButton(t("buttons.my_hosting", user_lang), callback_data="my_hosting")],
        [InlineKeyboardButton(t("buttons.back", user_lang), callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await effective_message.reply_text(message_text, reply_markup=reply_markup)


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /language command - show language selection interface"""
    user = update.effective_user
    effective_message = update.effective_message
    
    if not user or not effective_message:
        logger.error("Missing user or message in language command")
        return
    
    # MAINTENANCE MODE CHECK - Block non-admin users during maintenance
    from services.maintenance_manager import MaintenanceManager
    is_active = await MaintenanceManager.is_maintenance_active()
    if is_active and not is_admin_user(user.id):
        user_lang = await get_user_lang_fast(user, context)
        maintenance_message = await MaintenanceManager.get_maintenance_message(user_lang)
        await effective_message.reply_text(maintenance_message, parse_mode=ParseMode.HTML)
        logger.info(f"🔧 MAINTENANCE: Blocked /language command from non-admin user {user.id}")
        return
    
    # Check if user has completed onboarding
    if not await require_user_onboarding(update, context):
        return
    
    try:
        # Get current user language for the interface message
        current_lang = await get_user_lang_fast(user, context)
        
        # Show language selection interface
        # TODO: Update to use new language selection flow
        await effective_message.reply_text(
            "🌍 Language settings will be available soon. Currently using English.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(t("buttons.back", current_lang), callback_data="main_menu")
            ]])
        )
        logger.info(f"✅ Language selection shown to user {user.id}")
        
    except Exception as e:
        logger.error(f"Error in language command for user {user.id}: {e}")
        
        # Get user_lang for error message
        user_lang = await get_user_lang_fast(user, context)
        
        # Fallback message
        await effective_message.reply_text(
            t('errors.language_settings_load_failed', user_lang),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(t("buttons.try_again", user_lang), callback_data="language_selection")
            ]])
        )


async def dns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /dns command"""
    # Delegate to handlers_main for now
    from handlers_main import dns_command as _handler
    return await _handler(update, context)


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast command (admin)"""
    # Delegate to handlers_main for now  
    from handlers_main import broadcast_command as _handler
    return await _handler(update, context)


# ============================================================================
# Main Callback Router
# ============================================================================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback query handler - routes to appropriate handlers"""
    # Delegate to handlers_main for now (this is the central router)
    from handlers_main import handle_callback as _handler
    return await _handler(update, context)


# ============================================================================
# Dashboard & Menus
# ============================================================================

async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: Optional[Dict] = None):
    """Show main dashboard with wallet balance and menu options - Production-ready with event loop protection"""
    user = update.effective_user
    query = update.callback_query
    
    if not user:
        logger.error("Missing user in show_dashboard")
        return
    
    # PRODUCTION FIX: Add timeout and async protection for event loop stability
    async def _safe_dashboard_operation():
        # PERFORMANCE OPTIMIZATION: Parallel database queries to reduce timeout risk
        if user_data is None:
            # OPTIMIZED: Run all database queries in parallel instead of sequentially
            try:
                # Define all queries to run in parallel
                async def get_user_data():
                    return await get_or_create_user(
                        telegram_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name
                    )
                
                async def get_wallet():
                    return await get_user_wallet_balance(user.id)
                
                async def get_min_hosting():
                    result = await execute_query(
                        "SELECT MIN(monthly_price) as min_price FROM hosting_plans WHERE is_active = true"
                    )
                    return int(result[0]['min_price']) if result and result[0]['min_price'] else 40
                
                async def get_min_rdp():
                    result = await execute_query(
                        "SELECT MIN(our_monthly_price) as min_price FROM rdp_plans WHERE is_active = true"
                    )
                    return int(result[0]['min_price']) if result and result[0]['min_price'] else 60
                
                # Execute all queries in parallel with overall timeout
                results = await asyncio.wait_for(
                    asyncio.gather(
                        get_user_data(),
                        get_wallet(),
                        get_min_hosting(),
                        get_min_rdp(),
                        return_exceptions=True
                    ),
                    timeout=20.0  # PRODUCTION FIX: Allow time for Neon cold start (15s connect + 5s query)
                )
                
                # Extract results with fallbacks for any individual failures
                db_user = results[0] if not isinstance(results[0], Exception) else {'id': user.id}
                wallet_balance = results[1] if not isinstance(results[1], Exception) else 0.0
                min_hosting_price = results[2] if not isinstance(results[2], Exception) else 40
                min_rdp_price = results[3] if not isinstance(results[3], Exception) else 60
                
                # Log any individual query failures
                for i, (name, result) in enumerate([
                    ('user_data', results[0]), ('wallet', results[1]),
                    ('hosting_price', results[2]), ('rdp_price', results[3])
                ]):
                    if isinstance(result, Exception):
                        logger.warning(f"Dashboard query {name} failed for user {user.id}: {result}")
                
            except asyncio.TimeoutError:
                logger.warning(f"Dashboard parallel queries timeout for user {user.id}, using fallbacks")
                db_user = {'id': user.id}
                wallet_balance = 0.0
                min_hosting_price = 40
                min_rdp_price = 60
            except Exception as db_error:
                logger.warning(f"Dashboard database error for user {user.id}: {db_error}, using fallbacks")
                db_user = {'id': user.id}
                wallet_balance = 0.0
                min_hosting_price = 40
                min_rdp_price = 60
        else:
            # Use provided user_data (from optimized query) + fetch prices in parallel
            db_user = user_data
            wallet_balance = user_data['wallet_balance']
            
            # Still need to fetch min prices in parallel
            min_hosting_price = 40
            min_rdp_price = 60
            try:
                price_results = await asyncio.wait_for(
                    asyncio.gather(
                        execute_query("SELECT MIN(monthly_price) as min_price FROM hosting_plans WHERE is_active = true"),
                        execute_query("SELECT MIN(our_monthly_price) as min_price FROM rdp_plans WHERE is_active = true"),
                        return_exceptions=True
                    ),
                    timeout=5.0
                )
                # Extract hosting price safely
                if len(price_results) > 0 and not isinstance(price_results[0], BaseException):
                    hosting_rows = price_results[0]
                    if hosting_rows and len(hosting_rows) > 0 and hosting_rows[0].get('min_price'):
                        min_hosting_price = int(hosting_rows[0]['min_price'])
                
                # Extract RDP price safely
                if len(price_results) > 1 and not isinstance(price_results[1], BaseException):
                    rdp_rows = price_results[1]
                    if rdp_rows and len(rdp_rows) > 0 and rdp_rows[0].get('min_price'):
                        min_rdp_price = int(rdp_rows[0]['min_price'])
            except:
                pass
        
        balance_display = format_money(Decimal(str(wallet_balance)))
        platform_name = get_platform_name()
        user_lang = await get_user_lang_fast(user, context)
        
        # Check if user is admin using unified admin check
        is_admin = is_admin_user(user.id)
        
        # Create dashboard message with translations
        dashboard_message = t_fmt('dashboard.title', user_lang) + "\n\n"
        # Use t_html for safe user name display
        welcome_text, _ = t_html('dashboard.welcome_back', user_lang, name=user.first_name or 'User')
        dashboard_message += welcome_text + "\n\n"
        dashboard_message += t('dashboard.balance', user_lang, balance=balance_display) + "\n\n"
        dashboard_message += t('dashboard.what_to_do', user_lang)
        
        keyboard = [
            [InlineKeyboardButton(btn_t('search_domains', user_lang), callback_data="search_domains")],
            [InlineKeyboardButton(btn_t('my_domains', user_lang), callback_data="my_domains")],
            [InlineKeyboardButton(btn_t('wallet', user_lang), callback_data="wallet_main"), InlineKeyboardButton(btn_t('hosting_from_price', user_lang, price=str(min_hosting_price)), callback_data="unified_hosting_plans")],
            [InlineKeyboardButton(btn_t('rdp_from_price', user_lang, price=str(min_rdp_price)), callback_data="rdp_purchase_start")],
            [InlineKeyboardButton(btn_t('api_management', user_lang), callback_data="api_management_main")],
            [InlineKeyboardButton(btn_t('become_reseller', user_lang), callback_data="reseller_program")],
            [InlineKeyboardButton(btn_t('profile', user_lang), callback_data="profile_main"), InlineKeyboardButton(btn_t('change_language', user_lang), callback_data="language_selection_from_profile")],
            [InlineKeyboardButton(btn_t('contact_support', user_lang), callback_data="contact_support")]
        ]
        
        # Add admin commands for admin users
        if is_admin:
            dashboard_message += "\n\n" + t('admin.admin_panel', user_lang)
            keyboard.append([InlineKeyboardButton(btn_t('broadcast_message', user_lang), callback_data="admin_broadcast")])
            keyboard.append([InlineKeyboardButton(btn_t('credit_user_wallet', user_lang), callback_data="admin_credit_wallet")])
            keyboard.append([InlineKeyboardButton(btn_t('openprovider_accounts', user_lang), callback_data="admin_openprovider_accounts")])
            keyboard.append([InlineKeyboardButton("🔄 DNS Sync", callback_data="admin_dns_sync")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # PRODUCTION FIX: Send or edit message with timeout and retry protection
        if query:
            try:
                await asyncio.wait_for(
                    safe_edit_message(query, dashboard_message, reply_markup),
                    timeout=15.0  # 15 second timeout for Telegram operations
                )
            except asyncio.TimeoutError:
                logger.warning(f"Telegram edit timeout for user {user.id}, trying fallback")
                # Fallback to sending new message if edit times out
                await asyncio.wait_for(
                    context.bot.send_message(
                        chat_id=user.id,
                        text=dashboard_message,
                        reply_markup=reply_markup
                    ),
                    timeout=15.0
                )
        else:
            # Direct message with timeout protection
            if update.message:
                await asyncio.wait_for(
                    update.message.reply_text(
                        text=dashboard_message,
                        reply_markup=reply_markup
                    ),
                    timeout=15.0
                )
            else:
                await asyncio.wait_for(
                    context.bot.send_message(
                        chat_id=user.id,
                        text=dashboard_message,
                        reply_markup=reply_markup
                    ),
                    timeout=15.0
                )
        
        logger.info(f"Dashboard shown to user {user.id} with balance {balance_display}")
    
    try:
        # PRODUCTION FIX: Run the entire operation with overall timeout protection
        await asyncio.wait_for(_safe_dashboard_operation(), timeout=30.0)
        
    except asyncio.TimeoutError:
        logger.error(f"⚠️ PRODUCTION: Dashboard operation timed out for user {user.id} - using emergency fallback")
        # Emergency fallback for total timeout
        await _emergency_dashboard_fallback(update, context, user)
        
    except Exception as e:
        logger.error(f"⚠️ PRODUCTION: Dashboard error for user {user.id}: {e} - using emergency fallback")
        # Emergency fallback for any other error
        await _emergency_dashboard_fallback(update, context, user)


async def _emergency_dashboard_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    """Emergency fallback dashboard when main dashboard fails - Production resilience
    
    CRITICAL: This fallback must be 100% database-free to work even when DB is hanging
    """
    user_lang = 'en'
    try:
        # Try to get cached language, but don't wait
        if context.user_data and context.user_data.get('_cached_user_lang'):
            user_lang = context.user_data['_cached_user_lang']
    except:
        pass
    
    platform_name = get_platform_name()
    
    # Simple fallback message - no database calls
    dashboard_message = f"""🌐 {platform_name}

Welcome back, {user.first_name or 'User'}!

💰 Balance: Loading...

What would you like to do?"""
    
    keyboard = [
        [InlineKeyboardButton("🔍 Search Domains", callback_data="search_domains")],
        [InlineKeyboardButton("🌐 My Domains", callback_data="my_domains")],
        [InlineKeyboardButton("💰 Wallet", callback_data="wallet_main"), InlineKeyboardButton("🏠 Hosting", callback_data="unified_hosting_plans")],
        [InlineKeyboardButton("👤 Profile", callback_data="profile_main")],
        [InlineKeyboardButton("💬 Contact Support", callback_data="contact_support")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        query = update.callback_query
        if query:
            await query.edit_message_text(dashboard_message, reply_markup=reply_markup)
        elif update.message:
            await update.message.reply_text(dashboard_message, reply_markup=reply_markup)
        else:
            await context.bot.send_message(chat_id=user.id, text=dashboard_message, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Emergency dashboard fallback also failed for user {user.id}: {e}")


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
    """OPTIMIZED: Show terms and conditions acceptance screen (text only)"""
    start_time = time.perf_counter()
    
    user = update.effective_user
    
    if not user:
        logger.error("Missing user in show_terms_acceptance")
        return
    
    # Get user language with caching optimization
    user_lang = await get_user_lang_fast(user, context)
    platform_name = get_platform_name()
    
    # Translated terms message with proper placeholder substitution
    terms_title = t_fmt('terms.title', user_lang, platform_name=platform_name)
    terms_content = t_fmt('terms.content', user_lang)
    terms_message = terms_title + "\n\n" + terms_content

    keyboard = [
        [InlineKeyboardButton(btn_t('accept', user_lang), callback_data="terms:accept"),
         InlineKeyboardButton(btn_t('view_full', user_lang), callback_data="terms:view")],
        [InlineKeyboardButton(btn_t('decline', user_lang), callback_data="terms:decline")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Get chat_id once for all attempts
    chat_id = update.effective_chat.id if update.effective_chat else user.id
    
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=terms_message,
            reply_markup=reply_markup
        )
        elapsed = (time.perf_counter() - start_time) * 1000
        logger.info(f"⚡ TERMS SENT: User {user.id} in {elapsed:.1f}ms")
        
    except Exception as e:
        logger.error(f"Error sending terms message: {e}")
        # Final fallback with no formatting
        try:
            terms_title = t_fmt('terms.title', user_lang, platform_name=platform_name)
            terms_content = t_fmt('terms.content', user_lang)
            plain_message = terms_title + "\n\n" + terms_content
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=plain_message,
                reply_markup=reply_markup
            )
        except Exception as fallback_error:
            logger.error(f"Error in terms fallback: {fallback_error}")


async def handle_terms_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle terms acceptance callback"""
    from handlers_main import handle_terms_callback as _handler
    return await _handler(update, context)


async def show_terms_or_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show terms or dashboard based on user status"""
    from handlers_main import show_terms_or_dashboard as _handler
    return await _handler(update, context)


# ============================================================================
# Language Selection
# ============================================================================

async def show_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show language selection buttons for onboarding"""
    message = update.effective_message
    
    if not message:
        logger.error("No message object in show_language_selection")
        return False
    
    try:
        # Get supported languages
        supported_langs = get_supported_languages()
        
        # Create keyboard with language options
        keyboard = []
        for lang_code in supported_langs:
            # Use hardcoded language info for now
            lang_options = {
                'en': {'flag': '🇺🇸', 'name': 'English'},
                'fr': {'flag': '🇫🇷', 'name': 'Français'},
                'es': {'flag': '🇪🇸', 'name': 'Español'}
            }
            flag = lang_options.get(lang_code, {}).get('flag', '🌐')
            name = lang_options.get(lang_code, {}).get('name', lang_code.upper())
            keyboard.append([
                InlineKeyboardButton(f"{flag} {name}", callback_data=f"language_select_{lang_code}")
            ])
        
        # Get localized welcome message  
        platform_name = get_platform_name()
        # Use default English for initial selection screen since user hasn't chosen language yet
        selection_message = t('onboarding.language_selection', 'en', platform_name=platform_name)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text(selection_message, reply_markup=reply_markup)
        return True
        
    except Exception as e:
        logger.error(f"Error showing language selection: {e}")
        return False


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
