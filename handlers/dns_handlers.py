"""
DNS Handlers - DNS record management and wizard functionality

Handles:
- DNS record creation wizard (A, CNAME, TXT, MX)
- DNS record editing and deletion
- DNS dashboard display
- Nameserver management
- Cloudflare zone operations
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.common import (
    safe_edit_message,
    escape_content_for_display,
    escape_html,
    create_error_message,
    get_user_language_fast,
    smart_dns_callback,
    is_valid_ip_address,
    is_ip_proxyable,
    log_debug,
    log_info,
)

logger = logging.getLogger(__name__)

# ============================================================================
# DNS Wizard State Management
# ============================================================================

def clear_dns_wizard_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear all DNS wizard state from context"""
    keys_to_clear = [
        'dns_wizard',
        'expecting_custom_subdomain',
        'expecting_custom_subdomain_mx',
        'expecting_dns_content_input',
        'expecting_dns_ip_input',
    ]
    
    if context.user_data:
        for key in keys_to_clear:
            context.user_data.pop(key, None)
    
    log_debug(logger, "DNS wizard state cleared")


def get_wizard_state(context: ContextTypes.DEFAULT_TYPE) -> Optional[Dict]:
    """Get current DNS wizard state"""
    if context.user_data:
        return context.user_data.get('dns_wizard')
    return None


def set_wizard_state(context: ContextTypes.DEFAULT_TYPE, state: Dict) -> None:
    """Set DNS wizard state"""
    if context.user_data is not None:
        context.user_data['dns_wizard'] = state


# ============================================================================
# DNS Record Type Selection
# ============================================================================

async def show_dns_record_type_selection(
    query,
    domain: str,
    user_lang: str
) -> None:
    """Show DNS record type selection keyboard"""
    from localization import t
    from utils.keyboard_cache import get_dns_record_type_keyboard
    
    message = f"📋 <b>{t('dns.add_record_title', user_lang, domain=domain)}</b>\n\n"
    message += t('dns.select_record_type', user_lang)
    
    # Use cached keyboard
    keyboard = get_dns_record_type_keyboard(domain, user_lang)
    
    await safe_edit_message(query, message, reply_markup=keyboard)


# ============================================================================
# A Record Wizard
# ============================================================================

async def start_a_record_wizard(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    domain: str
) -> None:
    """Start A record creation wizard"""
    from localization import t
    from services.cloudflare import CloudflareService
    from database import get_cloudflare_zone
    
    user = query.from_user
    user_lang = await get_user_language_fast_from_query(query, context)
    
    # Initialize wizard state
    wizard_state = {
        'domain': domain,
        'action': 'add',
        'type': 'A',
        'step': 1,
        'data': {}
    }
    set_wizard_state(context, wizard_state)
    
    # Get available names for A records
    cf_zone = await get_cloudflare_zone(domain)
    if not cf_zone:
        await safe_edit_message(
            query,
            create_error_message(t('dns.dns_unavailable', user_lang, domain=domain), user_lang)
        )
        return
    
    zone_id = cf_zone['cf_zone_id']
    available_names = await get_available_names_for_record_type(domain, 'A', zone_id)
    
    if not available_names:
        await safe_edit_message(
            query,
            f"❌ <b>{t('domain.sections.no_available_names', user_lang)}</b>\n\n"
            f"{t('domain.sections.all_cname_conflict', user_lang)}"
        )
        return
    
    # Build name selection keyboard
    message = f"🅰️ <b>{t('dns_wizard.a_record_title', user_lang, step=1, domain=domain)}</b>\n\n"
    message += t('dns_wizard.choose_name', user_lang)
    
    keyboard = build_name_selection_keyboard(domain, 'A', available_names, user_lang)
    
    await safe_edit_message(query, message, reply_markup=keyboard)


async def continue_a_record_wizard(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    wizard_state: Dict
) -> None:
    """Continue A record wizard based on current state"""
    from localization import t
    from utils.keyboard_cache import get_ttl_selection_keyboard, get_proxy_selection_keyboard
    
    user_lang = await get_user_language_fast_from_query(query, context)
    domain = wizard_state['domain']
    data = wizard_state.get('data', {})
    
    log_debug(logger, "A record wizard step - data: %s", data)
    
    # Step 2: IP Address input
    if 'name' in data and 'ip' not in data:
        name_display = data['name'] if data['name'] != '@' else domain
        message = f"🅰️ <b>{t('dns_wizard.a_record_title', user_lang, step=2, domain=domain)}</b>\n\n"
        message += f"{t('common_labels.name', user_lang)}: {escape_html(name_display)}\n\n"
        message += t('dns_wizard.enter_ipv4', user_lang)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(t("buttons.use_8_8_8_8", user_lang), callback_data=f"dns_wizard:{domain}:A:ip:8.8.8.8")],
            [InlineKeyboardButton(t("buttons.use_1_1_1_1", user_lang), callback_data=f"dns_wizard:{domain}:A:ip:1.1.1.1")],
            [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:A:name:back")]
        ])
        
        # Set expectation for IP input
        if context.user_data is not None:
            context.user_data['expecting_dns_ip_input'] = {
                'domain': domain,
                'record_type': 'A',
                'wizard_state': wizard_state
            }
        
        await safe_edit_message(query, message, reply_markup=keyboard)
        return
    
    # Step 3: TTL selection
    if 'ip' in data and 'ttl' not in data:
        name_display = data['name'] if data['name'] != '@' else domain
        message = f"🅰️ <b>{t('dns_wizard.a_record_title', user_lang, step=3, domain=domain)}</b>\n\n"
        message += f"{t('common_labels.name', user_lang)}: {escape_html(name_display)}\n"
        message += f"IP: {data['ip']}\n\n"
        message += t('dns_wizard.select_ttl', user_lang)
        
        keyboard = get_ttl_selection_keyboard(domain, 'A', user_lang, 'ip')
        await safe_edit_message(query, message, reply_markup=keyboard)
        return
    
    # Step 4: Proxy selection
    if 'ttl' in data and 'proxied' not in data:
        name_display = data['name'] if data['name'] != '@' else domain
        ttl_display = "Auto" if data['ttl'] == 1 or data['ttl'] == '1' else f"{data['ttl']}s"
        can_proxy = is_ip_proxyable(data['ip'])
        
        message = f"🅰️ <b>{t('dns_wizard.a_record_title', user_lang, step=4, domain=domain)}</b>\n\n"
        message += f"{t('common_labels.name', user_lang)}: {escape_html(name_display)}\n"
        message += f"IP: {data['ip']}\n"
        message += f"TTL: {ttl_display}\n\n"
        
        if can_proxy:
            message += t('dns_wizard.proxy_setting', user_lang) + "\n\n"
            message += t('dns_wizard.proxy_explanation', user_lang)
        else:
            message += t('dns_wizard.proxy_not_available', user_lang)
        
        keyboard = get_proxy_selection_keyboard(domain, user_lang, can_proxy)
        await safe_edit_message(query, message, reply_markup=keyboard)
        return
    
    # Step 5: Confirmation
    if 'proxied' in data:
        await show_a_record_confirmation(query, context, wizard_state)
        return


async def show_a_record_confirmation(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    wizard_state: Dict
) -> None:
    """Show A record creation confirmation"""
    from localization import t
    
    user_lang = await get_user_language_fast_from_query(query, context)
    domain = wizard_state['domain']
    data = wizard_state['data']
    
    name_display = data['name'] if data['name'] != '@' else domain
    ttl_display = "Auto" if data['ttl'] in [1, '1'] else f"{data['ttl']}s"
    proxy_display = "🟠 Proxied" if data['proxied'] in ['true', True] else "⚪ Direct"
    
    message = f"✅ <b>{t('dns_wizard.confirm_a_record_creation', user_lang)}</b>\n\n"
    message += f"Domain: {domain}\n"
    message += f"{t('common_labels.name', user_lang)}: {escape_html(name_display)}\n"
    message += f"IP: {data['ip']}\n"
    message += f"TTL: {ttl_display}\n"
    message += f"Proxy: {proxy_display}\n\n"
    message += f"{t('dns_wizard.this_will_create', user_lang)}\n"
    message += f"{escape_html(name_display)} → {data['ip']}\n\n"
    message += t('dns_wizard.ready_to_create', user_lang)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("buttons.create_record", user_lang), callback_data=f"dns_wizard:{domain}:A:create:confirm")],
        [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:A:proxied:back")],
        [InlineKeyboardButton(t("buttons.cancel", user_lang), callback_data=f"dns:{domain}:view")]
    ])
    
    await safe_edit_message(query, message, reply_markup=keyboard)


# ============================================================================
# MX Record Wizard
# ============================================================================

async def start_mx_record_wizard(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    domain: str
) -> None:
    """Start MX record creation wizard"""
    from localization import t
    from database import get_cloudflare_zone
    
    user_lang = await get_user_language_fast_from_query(query, context)
    
    wizard_state = {
        'domain': domain,
        'action': 'add',
        'type': 'MX',
        'step': 1,
        'data': {}
    }
    set_wizard_state(context, wizard_state)
    
    # Get available names
    cf_zone = await get_cloudflare_zone(domain)
    if not cf_zone:
        await safe_edit_message(
            query,
            create_error_message(t('dns.dns_unavailable', user_lang, domain=domain), user_lang)
        )
        return
    
    zone_id = cf_zone['cf_zone_id']
    available_names = await get_available_names_for_record_type(domain, 'MX', zone_id)
    
    if not available_names:
        await safe_edit_message(
            query,
            f"❌ <b>{t('domain.sections.no_available_names', user_lang)}</b>"
        )
        return
    
    message = f"📧 <b>{t('dns_wizard.mx_record_title', user_lang, step=1, domain=domain)}</b>\n\n"
    message += t('dns_wizard.choose_name', user_lang)
    
    keyboard = build_name_selection_keyboard(domain, 'MX', available_names, user_lang)
    await safe_edit_message(query, message, reply_markup=keyboard)


async def continue_mx_record_wizard(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    wizard_state: Dict
) -> None:
    """Continue MX record wizard based on current state"""
    from localization import t
    from utils.keyboard_cache import get_mx_priority_keyboard, get_ttl_selection_keyboard
    
    user_lang = await get_user_language_fast_from_query(query, context)
    domain = wizard_state['domain']
    data = wizard_state.get('data', {})
    
    log_debug(logger, "MX wizard step - data: %s", data)
    
    # Check if name is set
    has_name = 'name' in data and data.get('name')
    
    if not has_name:
        # Back to name selection
        await start_mx_record_wizard(query, context, domain)
        return
    
    # Custom subdomain handling
    if data.get('name') == 'custom' and not data.get('custom_name_entered'):
        await show_custom_subdomain_prompt(query, context, domain, 'MX', user_lang)
        return
    
    # Step 2: Mail Server
    if 'server' not in data:
        name_display = data['name'] if data['name'] != '@' else domain
        safe_name = escape_content_for_display(name_display, mode='summary')[0]
        
        message = f"📧 <b>{t('dns_wizard.mx_record_title', user_lang, step=2, domain=domain)}</b>\n\n"
        message += f"{t('common_labels.name', user_lang)}: {safe_name}\n\n"
        message += t('dns_wizard.enter_mail_server', user_lang)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"mail.{domain}", callback_data=f"dns_wizard:{domain}:MX:server:mail.{domain}")],
            [InlineKeyboardButton(t("buttons.use_google_workspace", user_lang), callback_data=f"dns_wizard:{domain}:MX:server:aspmx.l.google.com")],
            [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:MX:name:back")]
        ])
        
        await safe_edit_message(query, message, reply_markup=keyboard)
        return
    
    # Step 3: Priority
    if 'priority' not in data:
        name_display = data['name'] if data['name'] != '@' else domain
        safe_name = escape_content_for_display(name_display, mode='summary')[0]
        safe_server = escape_content_for_display(data['server'], mode='summary')[0]
        
        message = f"📧 <b>{t('dns_wizard.mx_record_title', user_lang, step=3, domain=domain)}</b>\n\n"
        message += f"{t('common_labels.name', user_lang)}: {safe_name}\n"
        message += f"{t('common_labels.server', user_lang)}: {safe_server}\n\n"
        message += t('dns_wizard.select_priority', user_lang)
        
        keyboard = get_mx_priority_keyboard(domain, user_lang)
        await safe_edit_message(query, message, reply_markup=keyboard)
        return
    
    # Step 4: TTL
    if 'ttl' not in data:
        name_display = data['name'] if data['name'] != '@' else domain
        safe_name = escape_content_for_display(name_display, mode='summary')[0]
        safe_server = escape_content_for_display(data['server'], mode='summary')[0]
        
        message = f"📧 <b>{t('dns_wizard.mx_record_title', user_lang, step=4, domain=domain)}</b>\n\n"
        message += f"{t('common_labels.name', user_lang)}: {safe_name}\n"
        message += f"{t('common_labels.server', user_lang)}: {safe_server}\n"
        message += f"{t('common_labels.priority', user_lang)}: {data['priority']}\n\n"
        message += t('dns_wizard.select_ttl', user_lang)
        
        keyboard = get_ttl_selection_keyboard(domain, 'MX', user_lang, 'priority')
        await safe_edit_message(query, message, reply_markup=keyboard)
        return
    
    # Step 5: Confirmation
    await show_mx_record_confirmation(query, context, wizard_state)


async def show_mx_record_confirmation(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    wizard_state: Dict
) -> None:
    """Show MX record creation confirmation"""
    from localization import t
    
    user_lang = await get_user_language_fast_from_query(query, context)
    domain = wizard_state['domain']
    data = wizard_state['data']
    
    name_display = data['name'] if data['name'] != '@' else domain
    ttl_display = "Auto" if data['ttl'] in [1, '1'] else f"{data['ttl']}s"
    
    message = f"✅ <b>{t('dns_wizard.confirm_mx_record_creation', user_lang)}</b>\n\n"
    message += f"Domain: {domain}\n"
    message += f"{t('common_labels.name', user_lang)}: {escape_html(name_display)}\n"
    message += f"{t('common_labels.server', user_lang)}: {data['server']}\n"
    message += f"{t('common_labels.priority', user_lang)}: {data['priority']}\n"
    message += f"TTL: {ttl_display}\n\n"
    message += t('dns_wizard.ready_to_create', user_lang)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("buttons.create_record", user_lang), callback_data=f"dns_wizard:{domain}:MX:create:confirm")],
        [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:MX:ttl:back")],
        [InlineKeyboardButton(t("buttons.cancel", user_lang), callback_data=f"dns:{domain}:view")]
    ])
    
    await safe_edit_message(query, message, reply_markup=keyboard)


# ============================================================================
# Helper Functions
# ============================================================================

async def get_user_language_fast_from_query(query, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Get user language from callback query with caching"""
    from localization import resolve_user_language
    
    user = query.from_user
    if not user:
        return 'en'
    
    # Check context cache
    if context.user_data:
        cached = context.user_data.get('_cached_user_lang')
        if cached:
            return cached
    
    # Resolve
    telegram_lang = getattr(user, 'language_code', None)
    user_lang = await resolve_user_language(user.id, telegram_lang)
    
    # Cache
    if context.user_data is not None:
        context.user_data['_cached_user_lang'] = user_lang
    
    return user_lang


async def get_available_names_for_record_type(
    domain: str,
    record_type: str,
    zone_id: str
) -> List[Dict]:
    """
    Get available subdomain names for a record type.
    
    Returns list of dicts with 'name' and 'display' keys.
    """
    from services.cloudflare import CloudflareService
    
    cloudflare = CloudflareService()
    
    # Standard names to offer
    standard_names = [
        {'name': '@', 'display': f'@ (root)'},
        {'name': 'www', 'display': 'www'},
        {'name': 'api', 'display': 'api'},
        {'name': 'mail', 'display': 'mail'},
    ]
    
    # Get existing records to check conflicts
    existing_records = await cloudflare.list_dns_records(zone_id)
    existing_cnames = {r['name'] for r in existing_records if r.get('type') == 'CNAME'}
    
    # Filter out names that have CNAME conflicts
    available = []
    for name_info in standard_names:
        full_name = domain if name_info['name'] == '@' else f"{name_info['name']}.{domain}"
        
        # CNAME conflicts with A, MX, TXT records
        if record_type in ['A', 'MX', 'TXT'] and full_name in existing_cnames:
            continue
        
        available.append(name_info)
    
    return available


def build_name_selection_keyboard(
    domain: str,
    record_type: str,
    available_names: List[Dict],
    user_lang: str
) -> InlineKeyboardMarkup:
    """Build keyboard for name/subdomain selection"""
    from localization import t
    
    keyboard = []
    row = []
    
    for name_info in available_names[:6]:
        button = InlineKeyboardButton(
            name_info['display'],
            callback_data=f"dns_wizard:{domain}:{record_type}:name:{name_info['name']}"
        )
        row.append(button)
        
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    # Add custom subdomain option
    keyboard.append([
        InlineKeyboardButton(
            t("buttons.custom_subdomain", user_lang),
            callback_data=f"dns_wizard:{domain}:{record_type}:name:custom"
        )
    ])
    
    # Back button
    keyboard.append([
        InlineKeyboardButton(
            t("buttons.back", user_lang),
            callback_data=f"dns:{domain}:add"
        )
    ])
    
    return InlineKeyboardMarkup(keyboard)


async def show_custom_subdomain_prompt(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    domain: str,
    record_type: str,
    user_lang: str
) -> None:
    """Show prompt for custom subdomain input"""
    from localization import t
    
    message = f"✏️ <b>{t('dns_wizard.custom_subdomain_title', user_lang, domain=domain)}</b>\n\n"
    message += t('dns_wizard.custom_subdomain_examples', user_lang) + "\n"
    message += t('dns_wizard.custom_subdomain_root_tip', user_lang) + "\n\n"
    message += t('dns_wizard.custom_subdomain_rules', user_lang) + "\n\n"
    message += t('dns_wizard.type_your_subdomain', user_lang)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:{record_type}:name:back")]
    ])
    
    await safe_edit_message(query, message, reply_markup=keyboard)
    
    # Set expectation for custom input
    if context.user_data is not None:
        context.user_data[f'expecting_custom_subdomain_{record_type.lower()}'] = {
            'domain': domain,
            'wizard_state': get_wizard_state(context)
        }


# ============================================================================
# DNS Record Creation
# ============================================================================

async def create_dns_record_from_wizard(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    wizard_state: Dict
) -> None:
    """Create DNS record using wizard state"""
    from localization import t
    from services.cloudflare import CloudflareService
    from database import get_cloudflare_zone, save_dns_records_to_db
    
    user_lang = await get_user_language_fast_from_query(query, context)
    domain = wizard_state['domain']
    record_type = wizard_state['type']
    data = wizard_state['data']
    
    log_info(logger, "Creating %s record for %s", record_type, domain)
    
    # Show creating message
    await safe_edit_message(query, t('dns.creating_record', user_lang))
    
    # Get zone
    cf_zone = await get_cloudflare_zone(domain)
    if not cf_zone:
        await safe_edit_message(
            query,
            create_error_message(t('dns.dns_unavailable', user_lang, domain=domain), user_lang)
        )
        return
    
    zone_id = cf_zone['cf_zone_id']
    cloudflare = CloudflareService()
    
    # Prepare record data
    record_name = data['name'] if data['name'] != '@' else domain
    record_ttl = int(data['ttl']) if data['ttl'] != '1' else 1
    
    # Create based on type
    result = None
    if record_type == 'A':
        result = await cloudflare.create_dns_record(
            zone_id=zone_id,
            record_type='A',
            name=record_name,
            content=data['ip'],
            ttl=record_ttl,
            proxied=data['proxied'] in ['true', True]
        )
    elif record_type == 'MX':
        result = await cloudflare.create_dns_record(
            zone_id=zone_id,
            record_type='MX',
            name=record_name,
            content=data['server'],
            ttl=record_ttl,
            priority=int(data['priority'])
        )
    elif record_type == 'CNAME':
        result = await cloudflare.create_dns_record(
            zone_id=zone_id,
            record_type='CNAME',
            name=record_name,
            content=data['target'],
            ttl=record_ttl
        )
    elif record_type == 'TXT':
        result = await cloudflare.create_dns_record(
            zone_id=zone_id,
            record_type='TXT',
            name=record_name,
            content=data['content'],
            ttl=record_ttl
        )
    
    if result and result.get('success'):
        # Clear wizard state
        clear_dns_wizard_state(context)
        
        # Sync records to database
        try:
            all_records = await cloudflare.list_dns_records(zone_id)
            if all_records:
                await save_dns_records_to_db(domain, all_records)
        except Exception as e:
            log_warning(logger, "DNS sync failed: %s", e)
        
        # Show success
        name_display = data['name'] if data['name'] != '@' else domain
        content_display = data.get('ip') or data.get('server') or data.get('target') or data.get('content', '')
        
        message = f"✅ <b>{t('dns_wizard.record_created_title', user_lang, type=record_type)}</b>\n"
        message += f"{escape_html(name_display)} → {escape_html(content_display)}"
        
        if record_type == 'MX':
            message += f" ({t('common_labels.priority', user_lang)}: {data['priority']})"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(t("buttons.view_dns_dashboard", user_lang), callback_data=f"dns:{domain}:view")],
            [InlineKeyboardButton(t("buttons.add_another_record", user_lang), callback_data=f"dns:{domain}:add")]
        ])
        
        await safe_edit_message(query, message, reply_markup=keyboard)
    else:
        # Show error
        error_msg = "Unknown error"
        if result and result.get('errors'):
            error_msg = result['errors'][0].get('message', error_msg)
        
        await safe_edit_message(
            query,
            create_error_message(f"{t('dns.create_failed', user_lang)}: {error_msg}", user_lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("buttons.try_again", user_lang), callback_data=f"dns:{domain}:add:{record_type}")],
                [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns:{domain}:view")]
            ])
        )


def log_warning(logger_instance, message: str, *args):
    """Log warning with lazy formatting"""
    logger_instance.warning(message, *args)
