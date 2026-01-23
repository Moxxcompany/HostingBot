"""
Domain Handlers - Domain registration and management

Contains actual implementations for:
- Domain search interface
- User domains listing
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
    is_valid_domain,
    validate_domain_name,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Imports helper
# ============================================================================

def _get_imports():
    """Lazy imports to avoid circular dependencies"""
    from localization import t, btn_t
    from database import get_or_create_user, get_user_domains
    return t, btn_t, get_or_create_user, get_user_domains


async def get_user_lang_fast(user, context):
    """Get user language with caching"""
    from handlers.common import get_user_lang_fast as _get_user_lang_fast
    return await _get_user_lang_fast(user, context)


# ============================================================================
# Domain Search (Implemented)
# ============================================================================

async def show_search_interface(query, context=None):
    """Show domain search interface"""
    t, btn_t, _, _ = _get_imports()
    
    user_lang = await get_user_lang_fast(query.from_user, context)
    
    message = f"""
{t('domain.search.title', user_lang)}

{t('domain.search.prompt_line1', user_lang)}

{t('domain.search.prompt_line2', user_lang)}
"""
    keyboard = [
        [InlineKeyboardButton(t("buttons.back", user_lang), callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Set context to expect domain search input
    if context and context.user_data is not None:
        context.user_data['expecting_domain_search'] = True
    
    await safe_edit_message(query, message, reply_markup=reply_markup)


async def show_user_domains(query, context=None):
    """Show user's domains - simple placeholder"""
    t, _, _, _ = _get_imports()
    
    user_lang = await get_user_lang_fast(query.from_user, context)
    message = f"""
{t('domain.list.title', user_lang)}

{t('domain.list.loading', user_lang)}
"""
    await safe_edit_message(query, message)


async def show_user_domains_complete(query, context=None):
    """Show complete domains management interface with all user domains"""
    t, btn_t, get_or_create_user, get_user_domains = _get_imports()
    
    # Clear admin states when navigating to domains
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
        domains = await get_user_domains(user_record['id'])
        
        if not domains:
            message = f"{t('dashboard.domains_list_title', user_lang)}\n\n{t('dashboard.no_domains_message', user_lang)}"
            keyboard = [
                [InlineKeyboardButton(t("buttons.search_domains", user_lang), callback_data="search_domains")],
                [InlineKeyboardButton(t("buttons.back", user_lang), callback_data="main_menu")]
            ]
        else:
            message = f"{t('dashboard.domains_list_title', user_lang)}\n\n{t('dashboard.domain_count', user_lang, count=len(domains))}\n\n"
            keyboard = []
            
            for domain in domains:
                domain_name = domain['domain_name']
                status = domain['status']
                restriction = domain.get('registrar_restriction')
                
                # Determine emoji and status based on restriction
                if restriction:
                    emoji = "🔒"
                    status_text = t('common_labels.restricted', user_lang, fallback='Restricted')
                elif status == 'active':
                    emoji = "✅"
                    status_text = t(f'common_labels.{status}', user_lang) if status else status.title()
                else:
                    emoji = "⏳"
                    status_text = t(f'common_labels.{status}', user_lang) if status else status.title()
                
                message += f"{emoji} {domain_name} ({status_text})\n"
                keyboard.append([InlineKeyboardButton(f"🌐 {domain_name}", callback_data=f"dns_{domain_name}")])
            
            keyboard.extend([
                [InlineKeyboardButton(btn_t("register_new_domain", user_lang), callback_data="search_domains")],
                [InlineKeyboardButton(t("buttons.back", user_lang), callback_data="main_menu")]
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(query, message, reply_markup=reply_markup)
        
    except Exception as e:
        logger.error("Error showing domains interface: %s", e)
        await safe_edit_message(query, "❌ Error\n\nCould not load domains.")


# ============================================================================
# Domain Search Results (Delegated)
# ============================================================================

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search command"""
    from handlers_main import search_command as _handler
    return await _handler(update, context)


async def handle_domain_search(update: Update, context: ContextTypes.DEFAULT_TYPE, domain_name: str):
    """Handle domain search input"""
    from handlers_main import handle_domain_search as _handler
    return await _handler(update, context, domain_name)


async def show_domain_search_results(query, domain_name: str, context):
    """Show domain search results"""
    from handlers_main import show_domain_search_results as _handler
    return await _handler(query, domain_name, context)


# ============================================================================
# Domain Registration (Delegated)
# ============================================================================

async def start_domain_registration(query, context, domain_name: str):
    """Start domain registration flow"""
    from handlers_main import start_domain_registration as _handler
    return await _handler(query, context, domain_name)


async def show_domain_registration_payment(query, domain_name: str, price: float, context):
    """Show domain registration payment options"""
    from handlers_main import show_domain_registration_payment as _handler
    return await _handler(query, domain_name, price, context)


async def process_domain_registration_wallet(query, domain_name: str, context):
    """Process domain registration with wallet payment"""
    from handlers_main import process_domain_registration_wallet as _handler
    return await _handler(query, domain_name, context)


async def process_domain_registration_crypto(query, domain_name: str, crypto_type: str, context):
    """Process domain registration with crypto payment"""
    from handlers_main import process_domain_registration_crypto as _handler
    return await _handler(query, domain_name, crypto_type, context)


# ============================================================================
# Domain Management (Delegated)
# ============================================================================

async def domain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /domains command"""
    from handlers_main import domain_command as _handler
    return await _handler(update, context)


async def show_domain_management(query, domain_name: str, context=None):
    """Show domain management dashboard"""
    from handlers_main import show_domain_management as _handler
    return await _handler(query, domain_name, context)


async def show_domain_details(query, domain_name: str):
    """Show domain details"""
    from handlers_main import show_domain_details as _handler
    return await _handler(query, domain_name)


async def show_domain_renewal_options(query, domain_name: str, context):
    """Show domain renewal options"""
    from handlers_main import show_domain_renewal_options as _handler
    return await _handler(query, domain_name, context)


# ============================================================================
# Domain Linking (Delegated)
# ============================================================================

async def link_domain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /link command"""
    from handlers_main import link_domain_command as _handler
    return await _handler(update, context)


async def show_domain_linking_intro(user, message, user_lang: str):
    """Show domain linking introduction"""
    from handlers_main import show_domain_linking_intro as _handler
    return await _handler(user, message, user_lang)


async def handle_domain_linking_callback(query, callback_data: str, context, user_lang: str):
    """Handle domain linking callback"""
    from handlers_main import handle_domain_linking_callback as _handler
    return await _handler(query, callback_data, context, user_lang)


async def start_domain_linking_flow(query, context, user_lang: str):
    """Start domain linking flow"""
    from handlers_main import start_domain_linking_flow as _handler
    return await _handler(query, context, user_lang)


async def handle_domain_linking_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle domain linking text input"""
    from handlers_main import handle_domain_linking_text_input as _handler
    return await _handler(update, context)


async def initiate_domain_linking_process(user, message, domain_name: str, context, user_lang: str):
    """Initiate domain linking process"""
    from handlers_main import initiate_domain_linking_process as _handler
    return await _handler(user, message, domain_name, context, user_lang)


# ============================================================================
# Domain Analysis (Delegated)
# ============================================================================

async def analyze_domain_status(domain_name: str) -> Dict:
    """Analyze domain status"""
    from handlers_main import analyze_domain_status as _handler
    return await _handler(domain_name)


async def smart_domain_handler(query, context, plan_id: str):
    """Smart domain handler for hosting flow"""
    from handlers_main import smart_domain_handler as _handler
    return await _handler(query, context, plan_id)


# ============================================================================
# Helper Functions
# ============================================================================

def is_valid_domain_format(domain: str) -> bool:
    """Check if domain format is valid"""
    return is_valid_domain(domain)


def get_domain_validation_error(domain_name: str, user_lang: str = 'en') -> str:
    """Get domain validation error message"""
    t, _, _, _ = _get_imports()
    
    if not domain_name:
        return t('domain.validation.empty', user_lang, fallback='Please enter a domain name')
    
    if not is_valid_domain(domain_name):
        return t('domain.validation.invalid_format', user_lang, fallback='Invalid domain format')
    
    return ""
