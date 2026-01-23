"""
DNS Handlers - DNS record management and wizard functionality

Contains actual implementations for:
- DNS record creation wizard (A, CNAME, TXT, MX)
- DNS record confirmation dialogs
- DNS record editing and deletion
- DNS dashboard display
"""

import logging
from typing import Optional, Dict, List, Any, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.common import (
    safe_edit_message,
    escape_content_for_display,
    escape_html,
    is_ip_proxyable,
    clear_dns_wizard_state,
    clear_dns_wizard_custom_subdomain_state,
    get_wizard_state,
    set_wizard_state,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Imports from main module (will be removed as we migrate)
# ============================================================================

def _get_imports():
    """Lazy import to avoid circular dependencies"""
    from localization import t
    from database import get_cloudflare_zone
    from utils.keyboard_cache import get_ttl_selection_keyboard, get_mx_priority_keyboard
    return t, get_cloudflare_zone, get_ttl_selection_keyboard, get_mx_priority_keyboard


async def get_user_lang_fast(user, context):
    """Get user language with caching"""
    from handlers.common import get_user_lang_fast as _get_user_lang_fast
    return await _get_user_lang_fast(user, context)


# ============================================================================
# DNS Dashboard & Record Display (Delegated)
# ============================================================================

async def show_dns_dashboard(query, domain: str, context=None):
    """Show DNS management dashboard for a domain"""
    from handlers_main import show_dns_dashboard as _handler
    return await _handler(query, domain, context)


async def show_dns_records_list(query, domain: str, record_type: str = None):
    """Show list of DNS records"""
    from handlers_main import show_dns_records_list as _handler
    return await _handler(query, domain, record_type)


async def show_dns_record_details(query, domain: str, record_id: str):
    """Show details of a specific DNS record"""
    from handlers_main import show_dns_record_details as _handler
    return await _handler(query, domain, record_id)


async def show_dns_add_record_menu(query, domain: str, context):
    """Show DNS record type selection menu"""
    from handlers_main import show_dns_add_record_menu as _handler
    return await _handler(query, domain, context)


async def handle_dns_wizard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle DNS wizard callback interactions"""
    from handlers_main import handle_dns_wizard_callback as _handler
    return await _handler(update, context)


# ============================================================================
# Helper Functions (Implemented)
# ============================================================================

async def get_available_names_for_record_type(domain: str, record_type: str, zone_id: str) -> List[Dict]:
    """Get available subdomain names for a record type"""
    from handlers_main import get_available_names_for_record_type as _handler
    return await _handler(domain, record_type, zone_id)


# ============================================================================
# A Record Wizard (Implemented)
# ============================================================================

async def continue_a_record_wizard(query, context, wizard_state: Dict):
    """Continue A record creation wizard based on current data"""
    t, get_cloudflare_zone, get_ttl_selection_keyboard, _ = _get_imports()
    
    user = query.from_user
    user_lang = await get_user_lang_fast(user, context)
    
    domain = wizard_state['domain']
    data = wizard_state['data']
    
    # Initialize variables
    keyboard = None
    reply_markup = None
    message = None
    
    # Handle custom subdomain input prompt
    if data.get('name') == 'custom':
        message = f"""
✏️ <b>Custom Subdomain for {domain}</b>

Examples: www, api, server-1
(Use @ for root domain)

Letters/numbers/hyphens only, 1-63 chars
Cannot start/end with hyphen

Type your subdomain:
"""
        keyboard = [
            [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:A:name:back")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(query, message, reply_markup=reply_markup)
        
        # Set context to expect custom subdomain input
        context.user_data['expecting_custom_subdomain_a'] = {
            'domain': domain,
            'wizard_state': wizard_state
        }
        return
    
    if 'name' not in data:
        # Step 1: Dynamic Name Selection for A Record
        cf_zone = await get_cloudflare_zone(domain)
        if not cf_zone:
            await safe_edit_message(query, f"❌ {t('dns.dns_unavailable_title', user_lang)}\n\n{t('dns.no_zone_for', user_lang, domain=domain)}")
            return
            
        available_names = await get_available_names_for_record_type(domain, 'A', cf_zone['cf_zone_id'])
        
        if not available_names:
            await safe_edit_message(query, 
                f"❌ <b>{t('domain.sections.no_available_names', user_lang)}</b>\n\n"
                f"{t('domain.sections.all_cname_conflict', user_lang)}\n\n"
                f"{t('domain.sections.delete_cname_or_use_different', user_lang)}"
            )
            return
            
        message = f"🅰️ {t('dns_wizard.a_record_title', user_lang, step=1, domain=domain)}\n\n{t('dns_wizard.choose_name', user_lang)}"
        
        # Create dynamic buttons
        keyboard = []
        row = []
        for name_info in available_names[:6]:
            button_text = f"{name_info['display']}"
            row.append(InlineKeyboardButton(button_text, callback_data=f"dns_wizard:{domain}:A:name:{name_info['name']}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton(t("buttons.custom_subdomain", user_lang), callback_data=f"dns_wizard:{domain}:A:name:custom")])
        keyboard.append([InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns:{domain}:add")])
        
    elif 'ip' not in data:
        # Step 2: IP Address
        name_display = data['name'] if data['name'] != '@' else domain
        message = f"🅰️ {t('dns_wizard.a_record_title', user_lang, step=2, domain=domain)}\n\n" \
                  f"{t('common_labels.name', user_lang)}: {name_display}\n\n" \
                  f"{t('dns_wizard.enter_ipv4', user_lang)}"
        keyboard = [
            [InlineKeyboardButton(t("buttons.use_8_8_8_8", user_lang), callback_data=f"dns_wizard:{domain}:A:ip:8.8.8.8")],
            [InlineKeyboardButton(t("buttons.use_1_1_1_1", user_lang), callback_data=f"dns_wizard:{domain}:A:ip:1.1.1.1")],
            [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:A:name:back")]
        ]
        
    elif 'ttl' not in data:
        # Step 3: TTL - Use cached keyboard
        name_display = data['name'] if data['name'] != '@' else domain
        message = f"🅰️ {t('dns_wizard.a_record_title', user_lang, step=3, domain=domain)}\n\n" \
                  f"{t('common_labels.name', user_lang)}: {name_display}\n" \
                  f"IP: {data['ip']}\n\n" \
                  f"{t('dns_wizard.select_ttl', user_lang)}"
        reply_markup = get_ttl_selection_keyboard(domain, 'A', user_lang, 'ip')
        
    elif 'proxied' not in data:
        # Step 4: Proxy Setting
        name_display = data['name'] if data['name'] != '@' else domain
        ttl_display = "Auto" if data['ttl'] == 1 else f"{data['ttl']}s"
        ip_address = data['ip']
        can_proxy = is_ip_proxyable(ip_address)
        
        if can_proxy:
            message = f"🅰️ {t('dns_wizard.a_record_title', user_lang, step=4, domain=domain)}\n\n" \
                      f"{t('common_labels.name', user_lang)}: {name_display}\n" \
                      f"IP: {data['ip']}\n" \
                      f"TTL: {ttl_display}\n\n" \
                      f"{t('dns_wizard.proxy_setting', user_lang)}\n\n" \
                      f"{t('dns_wizard.proxy_explanation', user_lang)}"
            keyboard = [
                [InlineKeyboardButton(t("buttons.proxied_recommended", user_lang), callback_data=f"dns_wizard:{domain}:A:proxied:true")],
                [InlineKeyboardButton(t("buttons.direct", user_lang), callback_data=f"dns_wizard:{domain}:A:proxied:false")],
                [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:A:ttl:back")]
            ]
        else:
            message = f"🅰️ {t('dns_wizard.a_record_title', user_lang, step=4, domain=domain)}\n\n" \
                      f"{t('common_labels.name', user_lang)}: {name_display}\n" \
                      f"IP: {data['ip']}\n" \
                      f"TTL: {ttl_display}\n\n" \
                      f"{t('dns_wizard.proxy_not_available', user_lang)}"
            keyboard = [
                [InlineKeyboardButton(t("buttons.direct_only_option", user_lang), callback_data=f"dns_wizard:{domain}:A:proxied:false")],
                [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:A:ttl:back")]
            ]
    else:
        # Step 5: Confirmation
        await show_a_record_confirmation(query, context, wizard_state)
        return
    
    if reply_markup is None and keyboard is not None:
        reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await safe_edit_message(query, message, reply_markup=reply_markup)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise e


async def show_a_record_confirmation(query, context, wizard_state: Dict):
    """Show A record confirmation before creation"""
    t, _, _, _ = _get_imports()
    
    user = query.from_user
    user_lang = await get_user_lang_fast(user, context)
    
    domain = wizard_state['domain']
    data = wizard_state['data']
    
    name_display = data['name'] if data['name'] != '@' else domain
    ttl_display = "Auto" if data['ttl'] == 1 else f"{data['ttl']}s"
    proxy_display = "🟠 Proxied" if data['proxied'] == "true" else "⚪ Direct"
    
    message = f"✅ {t('dns_wizard.confirm_a_record_creation', user_lang)}\n\n" \
              f"Domain: {domain}\n" \
              f"{t('common_labels.name', user_lang)}: {name_display}\n" \
              f"IP: {data['ip']}\n" \
              f"TTL: {ttl_display}\n" \
              f"Proxy: {proxy_display}\n\n" \
              f"{t('dns_wizard.this_will_create', user_lang)}\n" \
              f"{name_display} → {data['ip']}\n\n" \
              f"{t('dns_wizard.ready_to_create', user_lang)}"
    
    keyboard = [
        [InlineKeyboardButton(t("buttons.create_record", user_lang), callback_data=f"dns_wizard:{domain}:A:create:confirm")],
        [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:A:proxied:back"),
         InlineKeyboardButton(t("buttons.cancel", user_lang), callback_data=f"dns:{domain}:view")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await safe_edit_message(query, message, reply_markup=reply_markup)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise e


# ============================================================================
# MX Record Wizard (Implemented)
# ============================================================================

async def continue_mx_record_wizard(query, context, wizard_state: Dict):
    """Continue MX record creation wizard"""
    t, get_cloudflare_zone, get_ttl_selection_keyboard, get_mx_priority_keyboard = _get_imports()
    
    user = query.from_user
    user_lang = await get_user_lang_fast(user, context)
    
    # Refresh wizard state from context
    if context.user_data and 'dns_wizard' in context.user_data:
        wizard_state = context.user_data['dns_wizard']
    
    domain = wizard_state['domain']
    data = wizard_state.get('data', {})
    
    keyboard = None
    reply_markup = None
    message = None
    
    # Handle custom subdomain
    if data.get('name') == 'custom' and not data.get('custom_entered'):
        message = f"""
✏️ <b>Custom Subdomain for MX Record</b>

Domain: {domain}

Enter subdomain name (or @ for root):
"""
        keyboard = [
            [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:MX:name:back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(query, message, reply_markup=reply_markup)
        
        context.user_data['expecting_custom_subdomain_mx'] = {
            'domain': domain,
            'wizard_state': wizard_state
        }
        return
    
    if 'name' not in data:
        # Step 1: Name selection
        cf_zone = await get_cloudflare_zone(domain)
        if not cf_zone:
            await safe_edit_message(query, f"❌ DNS not available for {domain}")
            return
        
        available_names = await get_available_names_for_record_type(domain, 'MX', cf_zone['cf_zone_id'])
        
        if not available_names:
            await safe_edit_message(query, f"❌ <b>{t('domain.sections.no_available_names', user_lang)}</b>")
            return
        
        message = f"📧 {t('dns_wizard.mx_record_title', user_lang, step=1, domain=domain)}\n\n{t('dns_wizard.choose_name', user_lang)}"
        
        keyboard = []
        row = []
        for name_info in available_names[:6]:
            row.append(InlineKeyboardButton(name_info['display'], callback_data=f"dns_wizard:{domain}:MX:name:{name_info['name']}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton(t("buttons.custom_subdomain", user_lang), callback_data=f"dns_wizard:{domain}:MX:name:custom")])
        keyboard.append([InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns:{domain}:add")])
        
    elif 'server' not in data:
        # Step 2: Mail server
        name_display = data['name'] if data['name'] != '@' else domain
        safe_name = escape_content_for_display(name_display, mode='summary')[0]
        
        message = f"📧 {t('dns_wizard.mx_record_title', user_lang, step=2, domain=domain)}\n\n" \
                  f"{t('common_labels.name', user_lang)}: {safe_name}\n\n" \
                  f"{t('dns_wizard.enter_mail_server', user_lang)}"
        
        keyboard = [
            [InlineKeyboardButton(f"mail.{domain}", callback_data=f"dns_wizard:{domain}:MX:server:mail.{domain}")],
            [InlineKeyboardButton(t("buttons.use_google_workspace", user_lang), callback_data=f"dns_wizard:{domain}:MX:server:aspmx.l.google.com")],
            [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:MX:name:back")]
        ]
        
    elif 'priority' not in data:
        # Step 3: Priority - Use cached keyboard
        name_display = data['name'] if data['name'] != '@' else domain
        server_preview = escape_content_for_display(data['server'], mode="summary")
        
        message = f"📧 {t('dns_wizard.mx_record_title', user_lang, step=3, domain=domain)}\n\n" \
                  f"{t('common_labels.name', user_lang)}: {escape_content_for_display(name_display, mode='summary')[0]}\n" \
                  f"{t('common_labels.server', user_lang)}: {server_preview[0] if isinstance(server_preview, tuple) else server_preview}\n\n" \
                  f"{t('dns_wizard.select_priority', user_lang)}"
        reply_markup = get_mx_priority_keyboard(domain, user_lang)
        
    elif 'ttl' not in data:
        # Step 4: TTL - Use cached keyboard
        name_display = data['name'] if data['name'] != '@' else domain
        server_preview = escape_content_for_display(data['server'], mode="summary")
        
        message = f"📧 {t('dns_wizard.mx_record_title', user_lang, step=4, domain=domain)}\n\n" \
                  f"{t('common_labels.name', user_lang)}: {escape_content_for_display(name_display, mode='summary')[0]}\n" \
                  f"{t('common_labels.server', user_lang)}: {server_preview[0] if isinstance(server_preview, tuple) else server_preview}\n" \
                  f"{t('common_labels.priority', user_lang)}: {data['priority']}\n\n" \
                  f"{t('dns_wizard.select_ttl', user_lang)}"
        reply_markup = get_ttl_selection_keyboard(domain, 'MX', user_lang, 'priority')
    else:
        # Step 5: Confirmation
        await show_mx_record_confirmation(query, context, wizard_state)
        return
    
    if reply_markup is None and keyboard is not None:
        reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await safe_edit_message(query, message, reply_markup=reply_markup)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise e


async def show_mx_record_confirmation(query, context, wizard_state: Dict):
    """Show MX record confirmation"""
    t, _, _, _ = _get_imports()
    
    user = query.from_user
    user_lang = await get_user_lang_fast(user, context)
    
    domain = wizard_state['domain']
    data = wizard_state['data']
    
    name_display = data['name'] if data['name'] != '@' else domain
    ttl_display = "Auto" if data['ttl'] == 1 else f"{data['ttl']}s"
    
    message = f"✅ {t('dns_wizard.confirm_mx_record_creation', user_lang)}\n\n" \
              f"Domain: {domain}\n" \
              f"Type: MX\n" \
              f"{t('common_labels.name', user_lang)}: {escape_html(name_display)}\n" \
              f"{t('common_labels.server', user_lang)}: {escape_html(data['server'])}\n" \
              f"{t('common_labels.priority', user_lang)}: {data['priority']}\n" \
              f"TTL: {ttl_display}\n\n" \
              f"{t('dns_wizard.ready_to_create', user_lang)}"
    
    keyboard = [
        [InlineKeyboardButton(t("buttons.create_record", user_lang), callback_data=f"dns_wizard:{domain}:MX:create:confirm")],
        [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:MX:ttl:back"),
         InlineKeyboardButton(t("buttons.cancel", user_lang), callback_data=f"dns:{domain}:view")]
    ]
    
    await safe_edit_message(query, message, reply_markup=InlineKeyboardMarkup(keyboard))


# ============================================================================
# CNAME Record Wizard (Implemented)
# ============================================================================

async def continue_cname_record_wizard(query, context, wizard_state: Dict):
    """Continue CNAME record wizard"""
    t, get_cloudflare_zone, get_ttl_selection_keyboard, _ = _get_imports()
    
    user = query.from_user
    user_lang = await get_user_lang_fast(user, context)
    
    domain = wizard_state['domain']
    data = wizard_state.get('data', {})
    
    keyboard = None
    reply_markup = None
    message = None
    
    if 'name' not in data:
        # Step 1: Name selection
        cf_zone = await get_cloudflare_zone(domain)
        if not cf_zone:
            await safe_edit_message(query, f"❌ DNS not available for {domain}")
            return
        
        available_names = await get_available_names_for_record_type(domain, 'CNAME', cf_zone['cf_zone_id'])
        
        message = f"🔗 {t('dns_wizard.cname_record_title', user_lang, step=1, domain=domain)}\n\n{t('dns_wizard.choose_name', user_lang)}"
        
        keyboard = []
        row = []
        for name_info in available_names[:6]:
            row.append(InlineKeyboardButton(name_info['display'], callback_data=f"dns_wizard:{domain}:CNAME:name:{name_info['name']}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton(t("buttons.custom_subdomain", user_lang), callback_data=f"dns_wizard:{domain}:CNAME:name:custom")])
        keyboard.append([InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns:{domain}:add")])
        
    elif 'target' not in data:
        # Step 2: Target
        name_display = data['name'] if data['name'] != '@' else domain
        
        message = f"🔗 {t('dns_wizard.cname_record_title', user_lang, step=2, domain=domain)}\n\n" \
                  f"{t('common_labels.name', user_lang)}: {escape_html(name_display)}\n\n" \
                  f"{t('dns_wizard.enter_target_domain', user_lang)}"
        
        keyboard = [
            [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:CNAME:name:back")]
        ]
        
    elif 'ttl' not in data:
        # Step 3: TTL - Use cached keyboard
        name_display = data['name'] if data['name'] != '@' else domain
        target_preview = escape_content_for_display(data['target'], mode="summary")
        
        message = f"🔗 {t('dns_wizard.cname_record_title', user_lang, step=3, domain=domain)}\n\n" \
                  f"{t('common_labels.name', user_lang)}: {escape_content_for_display(name_display, mode='summary')[0]}\n" \
                  f"{t('common_labels.target', user_lang)}: {target_preview[0] if isinstance(target_preview, tuple) else target_preview}\n\n" \
                  f"{t('dns_wizard.select_ttl', user_lang)}"
        reply_markup = get_ttl_selection_keyboard(domain, 'CNAME', user_lang, 'target')
    else:
        # Step 4: Confirmation
        await show_cname_record_confirmation(query, context, wizard_state)
        return
    
    if reply_markup is None and keyboard is not None:
        reply_markup = InlineKeyboardMarkup(keyboard)
    
    await safe_edit_message(query, message, reply_markup=reply_markup)


async def show_cname_record_confirmation(query, context, wizard_state: Dict):
    """Show CNAME record confirmation"""
    t, _, _, _ = _get_imports()
    
    user = query.from_user
    user_lang = await get_user_lang_fast(user, context)
    
    domain = wizard_state['domain']
    data = wizard_state['data']
    
    name_display = data['name'] if data['name'] != '@' else domain
    ttl_display = "Auto" if data['ttl'] == 1 else f"{data['ttl']}s"
    target_display = escape_content_for_display(data['target'], mode="full")[0]
    
    message = f"✅ {t('dns_wizard.confirm_cname_record_creation', user_lang)}\n\n" \
              f"Domain: {domain}\n" \
              f"Type: CNAME\n" \
              f"{t('common_labels.name', user_lang)}: {escape_html(name_display)}\n" \
              f"{t('common_labels.target', user_lang)}: {target_display}\n" \
              f"TTL: {ttl_display}\n\n" \
              f"{t('dns_wizard.ready_to_create', user_lang)}"
    
    keyboard = [
        [InlineKeyboardButton(t("buttons.create_record", user_lang), callback_data=f"dns_wizard:{domain}:CNAME:create:confirm")],
        [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:CNAME:ttl:back"),
         InlineKeyboardButton(t("buttons.cancel", user_lang), callback_data=f"dns:{domain}:view")]
    ]
    
    await safe_edit_message(query, message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


# ============================================================================
# TXT Record Wizard (Implemented)
# ============================================================================

async def continue_txt_record_wizard(query, context, wizard_state: Dict):
    """Continue TXT record wizard"""
    t, get_cloudflare_zone, get_ttl_selection_keyboard, _ = _get_imports()
    
    user = query.from_user
    user_lang = await get_user_lang_fast(user, context)
    
    domain = wizard_state['domain']
    data = wizard_state.get('data', {})
    
    keyboard = None
    reply_markup = None
    message = None
    
    if 'name' not in data:
        # Step 1: Name selection
        cf_zone = await get_cloudflare_zone(domain)
        if not cf_zone:
            await safe_edit_message(query, f"❌ DNS not available for {domain}")
            return
        
        available_names = await get_available_names_for_record_type(domain, 'TXT', cf_zone['cf_zone_id'])
        
        message = f"📝 {t('dns_wizard.txt_record_title', user_lang, step=1, domain=domain)}\n\n{t('dns_wizard.choose_name', user_lang)}"
        
        keyboard = []
        row = []
        for name_info in available_names[:6]:
            row.append(InlineKeyboardButton(name_info['display'], callback_data=f"dns_wizard:{domain}:TXT:name:{name_info['name']}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton(t("buttons.custom_subdomain", user_lang), callback_data=f"dns_wizard:{domain}:TXT:name:custom")])
        keyboard.append([InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns:{domain}:add")])
        
    elif 'content' not in data:
        # Step 2: Content
        name_display = data['name'] if data['name'] != '@' else domain
        
        message = f"📝 {t('dns_wizard.txt_record_title', user_lang, step=2, domain=domain)}\n\n" \
                  f"{t('common_labels.name', user_lang)}: {escape_html(name_display)}\n\n" \
                  f"{t('dns_wizard.enter_txt_content', user_lang)}"
        
        keyboard = [
            [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:TXT:name:back")]
        ]
        
    elif 'ttl' not in data:
        # Step 3: TTL - Use cached keyboard
        name_display = data['name'] if data['name'] != '@' else domain
        content_preview = escape_content_for_display(data['content'], mode="full")
        name_safe = escape_content_for_display(name_display, mode="full")
        
        message = f"📝 {t('dns_wizard.txt_record_title', user_lang, step=3, domain=domain)}\n\n" \
                  f"{name_safe[0]} → {content_preview[0]}\n\n" \
                  f"{t('dns_wizard.select_ttl', user_lang)}"
        reply_markup = get_ttl_selection_keyboard(domain, 'TXT', user_lang, 'content')
    else:
        # Step 4: Confirmation
        await show_txt_record_confirmation(query, context, wizard_state)
        return
    
    if reply_markup is None and keyboard is not None:
        reply_markup = InlineKeyboardMarkup(keyboard)
    
    await safe_edit_message(query, message, reply_markup=reply_markup)


async def show_txt_record_confirmation(query, context, wizard_state: Dict):
    """Show TXT record confirmation"""
    t, _, _, _ = _get_imports()
    
    user = query.from_user
    user_lang = await get_user_lang_fast(user, context)
    
    domain = wizard_state['domain']
    data = wizard_state['data']
    
    name_display = data['name'] if data['name'] != '@' else domain
    ttl_display = "Auto" if data['ttl'] == 1 else f"{data['ttl']}s"
    content_display = escape_content_for_display(data['content'], mode="full")[0]
    
    message = f"✅ {t('dns_wizard.confirm_txt_record_creation', user_lang)}\n\n" \
              f"Domain: {domain}\n" \
              f"Type: TXT\n" \
              f"{t('common_labels.name', user_lang)}: {escape_html(name_display)}\n" \
              f"{t('common_labels.content', user_lang)}: {content_display}\n" \
              f"TTL: {ttl_display}\n\n" \
              f"{t('dns_wizard.ready_to_create', user_lang)}"
    
    keyboard = [
        [InlineKeyboardButton(t("buttons.create_record", user_lang), callback_data=f"dns_wizard:{domain}:TXT:create:confirm")],
        [InlineKeyboardButton(t("buttons.back", user_lang), callback_data=f"dns_wizard:{domain}:TXT:ttl:back"),
         InlineKeyboardButton(t("buttons.cancel", user_lang), callback_data=f"dns:{domain}:view")]
    ]
    
    await safe_edit_message(query, message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


# ============================================================================
# DNS Record Operations (Delegated)
# ============================================================================

async def create_dns_record_from_wizard(query, context, wizard_state: Dict):
    """Create DNS record using wizard state"""
    from handlers_main import create_dns_record_from_wizard as _handler
    return await _handler(query, context, wizard_state)


async def show_dns_record_edit(query, domain: str, record_id: str, context):
    """Show DNS record edit interface"""
    from handlers_main import show_dns_record_edit as _handler
    return await _handler(query, domain, record_id, context)


async def confirm_dns_record_delete(query, domain: str, record_id: str, context):
    """Confirm DNS record deletion"""
    from handlers_main import confirm_dns_record_delete as _handler
    return await _handler(query, domain, record_id, context)


async def delete_dns_record(query, domain: str, record_id: str, context):
    """Delete DNS record"""
    from handlers_main import delete_dns_record as _handler
    return await _handler(query, domain, record_id, context)


# ============================================================================
# Nameserver Management (Delegated)
# ============================================================================

async def show_nameserver_management(query, domain_name: str, context):
    """Show nameserver management interface"""
    from handlers_main import show_nameserver_management as _handler
    return await _handler(query, domain_name, context)


async def confirm_switch_to_cloudflare_ns(query, domain_name: str):
    """Confirm switch to Cloudflare nameservers"""
    from handlers_main import confirm_switch_to_cloudflare_ns as _handler
    return await _handler(query, domain_name)


async def execute_switch_to_cloudflare_ns(query, context, domain_name: str):
    """Execute nameserver switch to Cloudflare"""
    from handlers_main import execute_switch_to_cloudflare_ns as _handler
    return await _handler(query, context, domain_name)
