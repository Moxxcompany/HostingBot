"""
Telegram Bot API Management Handlers
Provides complete UI for creating, managing, and documenting API keys
"""

import logging
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import execute_query, execute_update
from localization import t, t_for_user, resolve_user_language
from message_utils import escape_html, format_bold
from unified_user_id_handlers import get_internal_user_id_from_telegram_id

logger = logging.getLogger(__name__)

MAX_API_KEYS_PER_USER = 5
DEFAULT_RATE_LIMIT_HOUR = 1000
DEFAULT_RATE_LIMIT_DAY = 10000

API_PERMISSION_RESOURCES = [
    ("domains", "📂 Domains"),
    ("dns", "🌐 DNS Management"),
    ("hosting", "🏠 Hosting"),
    ("wallet", "💰 Wallet"),
    ("api_keys", "🔑 API Keys")
]


async def show_api_management_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show API Management dashboard with list of API keys or empty state."""
    query = update.callback_query
    if query:
        await query.answer()
    
    user = update.effective_user
    user_lang = await resolve_user_language(user.id, user.language_code)
    
    try:
        internal_user_id = await get_internal_user_id_from_telegram_id(user.id)
        if not internal_user_id:
            await query.edit_message_text(
                text=t('errors.user_not_found', user_lang),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(t('buttons.back', user_lang), callback_data="main_menu")
                ]])
            )
            return
        
        api_keys_result = await execute_query("""
            SELECT id, key_prefix, name, permissions, rate_limit_per_hour, rate_limit_per_day,
                   last_used_at, created_at, is_active, ip_whitelist
            FROM api_keys
            WHERE user_id = %s AND is_active = true AND revoked_at IS NULL
            ORDER BY created_at DESC
        """, (internal_user_id,))
        
        usage_stats = {}
        if api_keys_result:
            for key in api_keys_result:
                stats = await execute_query("""
                    SELECT COUNT(*) as total_requests,
                           SUM(CASE WHEN status_code >= 200 AND status_code < 400 THEN 1 ELSE 0 END) as successful,
                           COUNT(CASE WHEN created_at > NOW() - INTERVAL '1 hour' THEN 1 END) as hourly_requests
                    FROM api_usage_logs
                    WHERE api_key_id = %s
                """, (key['id'],))
                
                if stats and stats[0]:
                    usage_stats[key['id']] = {
                        'total': stats[0]['total_requests'] or 0,
                        'successful': stats[0]['successful'] or 0,
                        'hourly': stats[0]['hourly_requests'] or 0
                    }
        
        if not api_keys_result:
            message = f"🔧 {format_bold(await t_for_user('api.dashboard.title', user.id))}\n\n"
            message += f"🔑 {await t_for_user('api.dashboard.no_keys_title', user.id)}\n\n"
            message += f"{await t_for_user('api.dashboard.no_keys_description', user.id)}\n\n"
            message += f"{await t_for_user('api.dashboard.endpoints_info', user.id, limit=DEFAULT_RATE_LIMIT_HOUR)}\n\n"
            message += f"💡 {await t_for_user('api.dashboard.perfect_for', user.id)}"
            
            keyboard = [
                [InlineKeyboardButton(await t_for_user('api.buttons.create_first', user.id), callback_data="api_create_start")],
                [InlineKeyboardButton(await t_for_user('api.buttons.view_docs', user.id), callback_data="api_docs_main")],
                [InlineKeyboardButton(await t_for_user('api.buttons.back_main', user.id), callback_data="main_menu")]
            ]
        else:
            message = f"🔧 {format_bold(await t_for_user('api.dashboard.title', user.id))}\n\n"
            message += f"📊 {await t_for_user('api.dashboard.active_keys', user.id, count=len(api_keys_result), max=MAX_API_KEYS_PER_USER)}\n\n"
            
            keyboard = []
            
            for key in api_keys_result:
                key_id = key['id']
                key_name = escape_html(key['name'])
                key_prefix = key['key_prefix']
                created_at = key['created_at'].strftime("%b %d, %Y") if key['created_at'] else "Unknown"
                last_used = key['last_used_at']
                
                stats = usage_stats.get(key_id, {'total': 0, 'successful': 0, 'hourly': 0})
                
                if last_used:
                    now_utc = datetime.now(timezone.utc)
                    if last_used.tzinfo is None:
                        last_used = last_used.replace(tzinfo=timezone.utc)
                    time_diff = now_utc - last_used
                    if time_diff.days > 0:
                        last_used_str = await t_for_user('api.dashboard.time_days_ago', user.id, days=time_diff.days)
                    elif time_diff.seconds > 3600:
                        last_used_str = await t_for_user('api.dashboard.time_hours_ago', user.id, hours=time_diff.seconds // 3600)
                    else:
                        last_used_str = await t_for_user('api.dashboard.time_minutes_ago', user.id, minutes=time_diff.seconds // 60)
                else:
                    last_used_str = await t_for_user('api.dashboard.last_used_never', user.id)
                
                message += f"🔑 {format_bold(key_name)}\n"
                message += f"   {await t_for_user('api.dashboard.key_prefix', user.id, prefix=key_prefix)}\n"
                message += f"   {await t_for_user('api.dashboard.created', user.id, date=created_at)}\n"
                message += f"   {await t_for_user('api.dashboard.last_used', user.id, time=last_used_str)}\n"
                message += f"   {await t_for_user('api.dashboard.requests_hourly', user.id, current=stats['hourly'], limit=key['rate_limit_per_hour'] or DEFAULT_RATE_LIMIT_HOUR)}\n\n"
                
                keyboard.append([
                    InlineKeyboardButton(await t_for_user('api.buttons.manage', user.id), callback_data=f"api_manage_{key_id}"),
                    InlineKeyboardButton(await t_for_user('api.buttons.stats', user.id), callback_data=f"api_stats_{key_id}")
                ])
            
            if len(api_keys_result) < MAX_API_KEYS_PER_USER:
                keyboard.append([InlineKeyboardButton(await t_for_user('api.buttons.create_new', user.id), callback_data="api_create_start")])
            
            keyboard.append([InlineKeyboardButton(await t_for_user('api.buttons.api_docs', user.id), callback_data="api_docs_main")])
            keyboard.append([InlineKeyboardButton(await t_for_user('api.buttons.back_main', user.id), callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query:
            await query.edit_message_text(text=message, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await update.message.reply_text(text=message, reply_markup=reply_markup, parse_mode='HTML')
    
    except Exception as e:
        logger.error(f"Error showing API management dashboard: {e}")
        error_msg = await t_for_user('api.errors.dashboard_error', user.id)
        keyboard = [[InlineKeyboardButton(await t_for_user('api.buttons.back', user.id), callback_data="main_menu")]]
        
        if query:
            await query.edit_message_text(text=error_msg, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(text=error_msg, reply_markup=InlineKeyboardMarkup(keyboard))


async def start_api_key_creation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Step 1: Ask user to name the API key."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_lang = await resolve_user_language(user.id, user.language_code)
    
    internal_user_id = await get_internal_user_id_from_telegram_id(user.id)
    if not internal_user_id:
        await query.edit_message_text(text=t('errors.user_not_found', user_lang))
        return
    
    existing_keys = await execute_query("""
        SELECT COUNT(*) as count FROM api_keys 
        WHERE user_id = %s AND is_active = true AND revoked_at IS NULL
    """, (internal_user_id,))
    
    if existing_keys and existing_keys[0]['count'] >= MAX_API_KEYS_PER_USER:
        await query.edit_message_text(
            text=await t_for_user('api.create.max_keys_reached', user.id, max=MAX_API_KEYS_PER_USER),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(await t_for_user('api.buttons.back', user.id), callback_data="api_management_main")
            ]])
        )
        return
    
    context.user_data['api_creation_step'] = 'name'
    
    message = f"➕ {format_bold(await t_for_user('api.create.title', user.id))}\n\n"
    message += f"{await t_for_user('api.create.name_prompt', user.id)}\n\n"
    message += f"{await t_for_user('api.create.examples_title', user.id)}\n"
    message += f"  • {await t_for_user('api.create.example_production', user.id)}\n"
    message += f"  • {await t_for_user('api.create.example_testing', user.id)}\n"
    message += f"  • {await t_for_user('api.create.example_mobile', user.id)}\n"
    message += f"  • {await t_for_user('api.create.example_automation', user.id)}\n\n"
    message += f"💡 {await t_for_user('api.create.tip', user.id)}\n\n"
    message += f"📝 {await t_for_user('api.create.enter_name', user.id)}"
    
    keyboard = [[InlineKeyboardButton(await t_for_user('api.buttons.cancel', user.id), callback_data="api_management_main")]]
    
    await query.edit_message_text(text=message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def handle_api_key_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process API key name and move to permissions selection."""
    if context.user_data.get('api_creation_step') != 'name':
        return
    
    user = update.effective_user
    user_lang = await resolve_user_language(user.id, user.language_code)
    
    key_name = update.message.text.strip()
    
    if len(key_name) < 3:
        await update.message.reply_text(await t_for_user('api.create.name_too_short', user.id))
        return
    
    if len(key_name) > 100:
        await update.message.reply_text(await t_for_user('api.create.name_too_long', user.id))
        return
    
    context.user_data['api_key_name'] = key_name
    context.user_data['api_creation_step'] = 'environment'
    context.user_data['api_environment'] = 'production'  # Default to production
    
    await show_environment_selector(update, context)


def get_permissions_for_environment(environment: str) -> dict:
    """Convert environment type to permission set."""
    if environment == 'staging':
        # Staging: Read-only access to everything (safe for testing)
        return {
            'domains': {'read': True, 'write': False},
            'dns': {'read': True, 'write': False},
            'hosting': {'read': True, 'write': False},
            'wallet': {'read': True, 'write': False},
            'api_keys': {'read': True, 'write': False},
            'nameservers': {'read': True, 'write': False}
        }
    else:  # production
        # Production: Full access to everything
        return {
            'domains': {'read': True, 'write': True},
            'dns': {'read': True, 'write': True},
            'hosting': {'read': True, 'write': True},
            'wallet': {'read': True, 'write': True},
            'api_keys': {'read': True, 'write': True},
            'nameservers': {'read': True, 'write': True}
        }


async def show_environment_selector(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show environment (Staging/Production) selection interface."""
    user = update.effective_user
    key_name = context.user_data.get('api_key_name', 'New API Key')
    environment = context.user_data.get('api_environment', 'production')
    
    staging_icon = "🔘" if environment == 'staging' else "⚪"
    production_icon = "🔘" if environment == 'production' else "⚪"
    
    env_title = await t_for_user('api.environment.title', user.id)
    message = f"🔐 {format_bold(env_title)}\n\n"
    message += f"{await t_for_user('api.environment.key_name', user.id, name=escape_html(key_name))}\n\n"
    message += f"{await t_for_user('api.environment.choose_prompt', user.id)}\n\n"
    
    staging_title = await t_for_user("api.environment.staging_title", user.id)
    message += f"{staging_icon} {format_bold('🧪 ' + staging_title)}\n"
    message += f"   • {await t_for_user('api.environment.staging_read_only', user.id)}\n"
    message += f"   • {await t_for_user('api.environment.staging_no_spend', user.id)}\n"
    message += f"   • {await t_for_user('api.environment.staging_no_modify', user.id)}\n"
    message += f"   • {await t_for_user('api.environment.staging_perfect', user.id)}\n\n"
    
    production_title = await t_for_user("api.environment.production_title", user.id)
    message += f"{production_icon} {format_bold('🚀 ' + production_title)}\n"
    message += f"   • {await t_for_user('api.environment.production_full_access', user.id)}\n"
    message += f"   • {await t_for_user('api.environment.production_can_spend', user.id)}\n"
    message += f"   • {await t_for_user('api.environment.production_live', user.id)}\n\n"
    
    message += f"💡 {await t_for_user('api.environment.tip', user.id)}"
    
    keyboard = [
        [InlineKeyboardButton(f"{staging_icon} {await t_for_user('api.environment.staging_button', user.id)}", callback_data="api_env_staging")],
        [InlineKeyboardButton(f"{production_icon} {await t_for_user('api.environment.production_button', user.id)}", callback_data="api_env_production")],
        [InlineKeyboardButton(await t_for_user('api.buttons.cancel', user.id), callback_data="api_management_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text=message, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(text=message, reply_markup=reply_markup, parse_mode='HTML')


async def toggle_environment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Select environment and immediately generate API key."""
    query = update.callback_query
    user = update.effective_user
    
    callback_data = query.data
    environment = callback_data.split('_')[2]  # api_env_staging or api_env_production
    
    # Set the environment
    context.user_data['api_environment'] = environment
    
    # Show friendly acknowledgment
    env_name = await t_for_user('api.environment.production_title' if environment == "production" else 'api.environment.staging_title', user.id)
    await query.answer(await t_for_user('api.environment.selected', user.id, environment=env_name), show_alert=False)
    
    # Directly generate the API key (skip security settings step)
    await generate_and_show_api_key(update, context)


async def show_security_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show IP whitelisting configuration."""
    query = update.callback_query
    await query.answer()
    
    key_name = context.user_data.get('api_key_name', 'New API Key')
    ip_whitelist = context.user_data.get('api_ip_whitelist', [])
    
    message = f"🔒 {format_bold('Security Settings')}\n\n"
    message += f"API Key: {format_bold(escape_html(key_name))}\n\n"
    message += "IP Address Whitelisting (Optional)\n\n"
    message += "Restrict this API key to specific IP addresses for extra security.\n\n"
    
    if ip_whitelist:
        message += "Current whitelist:\n"
        for ip in ip_whitelist:
            message += f"  • {ip}\n"
        message += "\n"
    else:
        message += "Current setting:\n"
        message += "🌍 Allow from any IP (default)\n\n"
    
    message += "💡 Recommended for production: Add your server's IP address\n"
    
    keyboard = [
        [InlineKeyboardButton("🔒 Add IP Whitelist", callback_data="api_add_ip")],
        [InlineKeyboardButton("⏭️ Skip (Use Default)", callback_data="api_create_generate")],
        [InlineKeyboardButton("⬅️ Back", callback_data="api_create_environment")]
    ]
    
    await query.edit_message_text(text=message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def generate_and_show_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate the API key and show it to the user (one-time display)."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_lang = await resolve_user_language(user.id, user.language_code)
    
    try:
        internal_user_id = await get_internal_user_id_from_telegram_id(user.id)
        if not internal_user_id:
            await query.edit_message_text(text=t('errors.user_not_found', user_lang))
            return
        
        key_name = context.user_data.get('api_key_name')
        environment = context.user_data.get('api_environment', 'production')
        permissions = get_permissions_for_environment(environment)
        ip_whitelist = context.user_data.get('api_ip_whitelist', [])
        
        raw_key = secrets.token_urlsafe(32)
        api_key = f"hbay_live_{raw_key}"
        
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_prefix = api_key[:15]
        
        import json
        
        await execute_update("""
            INSERT INTO api_keys (
                user_id, key_hash, key_prefix, name, environment, permissions,
                rate_limit_per_hour, rate_limit_per_day,
                ip_whitelist, created_at, is_active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, true)
        """, (
            internal_user_id, key_hash, key_prefix, key_name, environment,
            json.dumps(permissions), DEFAULT_RATE_LIMIT_HOUR, DEFAULT_RATE_LIMIT_DAY,
            json.dumps(ip_whitelist) if ip_whitelist else None
        ))
        
        context.user_data.pop('api_creation_step', None)
        context.user_data.pop('api_key_name', None)
        context.user_data.pop('api_environment', None)
        context.user_data.pop('api_ip_whitelist', None)
        
        message = f"✅ {format_bold(await t_for_user('api.generated.title', user.id))}\n\n"
        message += f"🔑 {await t_for_user('api.generated.your_key', user.id)}\n"
        message += f"<code>{escape_html(api_key)}</code>\n\n"
        message += f"⚠️ {await t_for_user('api.generated.important', user.id)}\n"
        message += f"{await t_for_user('api.generated.save_now', user.id)}\n\n"
        message += f"📚 {await t_for_user('api.generated.getting_started', user.id)}\n"
        message += f"1. {await t_for_user('api.generated.step1', user.id)}\n"
        message += f"2. {await t_for_user('api.generated.step2', user.id, key=escape_html(api_key[:20]))}\n"
        message += f"3. {await t_for_user('api.generated.step3', user.id)}\n"
        
        keyboard = [
            [InlineKeyboardButton(await t_for_user('api.buttons.view_docs', user.id), callback_data="api_docs_main")],
            [InlineKeyboardButton(await t_for_user('api.buttons.saved_key', user.id), callback_data="api_management_main")]
        ]
        
        await query.edit_message_text(text=message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
        logger.info(f"API key created for user {user.id}: {key_name}")
    
    except Exception as e:
        logger.error(f"Error generating API key: {e}")
        await query.edit_message_text(
            text=await t_for_user('api.errors.create_error', user.id),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(await t_for_user('api.buttons.back', user.id), callback_data="api_management_main")
            ]])
        )


async def show_api_key_management(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show management options for a specific API key."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_lang = await resolve_user_language(user.id, user.language_code)
    
    key_id = int(query.data.split('_')[-1])
    
    try:
        internal_user_id = await get_internal_user_id_from_telegram_id(user.id)
        
        key_result = await execute_query("""
            SELECT id, key_prefix, name, permissions, rate_limit_per_hour, rate_limit_per_day,
                   last_used_at, created_at, ip_whitelist
            FROM api_keys
            WHERE id = %s AND user_id = %s AND is_active = true AND revoked_at IS NULL
        """, (key_id, internal_user_id))
        
        if not key_result:
            await query.edit_message_text(
                text=await t_for_user('api.errors.key_not_found', user.id),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(await t_for_user('api.buttons.back', user.id), callback_data="api_management_main")
                ]])
            )
            return
        
        key = key_result[0]
        
        stats = await execute_query("""
            SELECT COUNT(*) as total_requests,
                   SUM(CASE WHEN status_code >= 200 AND status_code < 400 THEN 1 ELSE 0 END) as successful
            FROM api_usage_logs
            WHERE api_key_id = %s
        """, (key_id,))
        
        total_requests = stats[0]['total_requests'] if stats and stats[0] else 0
        
        message = f"⚙️ {format_bold(await t_for_user('api.manage.title', user.id))}\n\n"
        message += f"🔑 {format_bold(escape_html(key['name']))}\n\n"
        message += f"📊 {await t_for_user('api.manage.usage_stats', user.id)}\n"
        message += f"  • {await t_for_user('api.manage.created', user.id, date=key['created_at'].strftime('%b %d, %Y'))}\n"
        
        if key['last_used_at']:
            message += f"  • {await t_for_user('api.manage.last_used', user.id, time=key['last_used_at'].strftime('%b %d, %Y %H:%M'))}\n"
        else:
            message += f"  • {await t_for_user('api.manage.last_used', user.id, time=await t_for_user('api.manage.last_used_never', user.id))}\n"
        
        message += f"  • {await t_for_user('api.manage.total_requests', user.id, count=total_requests)}\n"
        message += f"  • {await t_for_user('api.manage.rate_limit', user.id, limit=key['rate_limit_per_hour'])}\n\n"
        
        message += f"🔐 {await t_for_user('api.manage.environment_title', user.id)}\n"
        permissions = key['permissions'] or {}
        
        # Determine environment based on wallet write permission
        # Staging = read-only (no wallet write), Production = full access (wallet write)
        is_production = permissions.get('wallet', {}).get('write', False)
        
        if is_production:
            message += f"  • 🚀 {await t_for_user('api.manage.production_full', user.id)}\n"
            message += f"  • {await t_for_user('api.manage.production_desc', user.id)}\n"
        else:
            message += f"  • 🧪 {await t_for_user('api.manage.staging_safe', user.id)}\n"
            message += f"  • {await t_for_user('api.manage.staging_desc', user.id)}\n"
        
        message += f"\n🔒 {await t_for_user('api.manage.security_title', user.id)}\n"
        if key['ip_whitelist']:
            message += f"  • {await t_for_user('api.manage.ip_whitelist', user.id, count=len(key['ip_whitelist']))}\n"
        else:
            message += f"  • {await t_for_user('api.manage.ip_whitelist_none', user.id)}\n"
        
        keyboard = [
            [InlineKeyboardButton(await t_for_user('api.buttons.view_usage', user.id), callback_data=f"api_stats_{key_id}")],
            [InlineKeyboardButton(await t_for_user('api.buttons.revoke', user.id), callback_data=f"api_revoke_{key_id}")],
            [InlineKeyboardButton(await t_for_user('api.buttons.back', user.id), callback_data="api_management_main")]
        ]
        
        await query.edit_message_text(text=message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    
    except Exception as e:
        logger.error(f"Error showing API key management: {e}")
        await query.edit_message_text(
            text=await t_for_user('api.errors.details_error', user.id),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(await t_for_user('api.buttons.back', user.id), callback_data="api_management_main")
            ]])
        )


async def show_api_key_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show detailed usage statistics for an API key."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    key_id = int(query.data.split('_')[-1])
    
    try:
        internal_user_id = await get_internal_user_id_from_telegram_id(user.id)
        
        key_result = await execute_query("""
            SELECT name FROM api_keys
            WHERE id = %s AND user_id = %s AND is_active = true
        """, (key_id, internal_user_id))
        
        if not key_result:
            await query.edit_message_text(text=await t_for_user('api.errors.key_not_found', user.id))
            return
        
        key_name = key_result[0]['name']
        
        stats_24h = await execute_query("""
            SELECT 
                COUNT(*) as total_requests,
                SUM(CASE WHEN status_code >= 200 AND status_code < 400 THEN 1 ELSE 0 END) as successful,
                AVG(response_time_ms) as avg_response
            FROM api_usage_logs
            WHERE api_key_id = %s AND created_at > NOW() - INTERVAL '24 hours'
        """, (key_id,))
        
        top_endpoints = await execute_query("""
            SELECT endpoint, method, COUNT(*) as count
            FROM api_usage_logs
            WHERE api_key_id = %s AND created_at > NOW() - INTERVAL '24 hours'
            GROUP BY endpoint, method
            ORDER BY count DESC
            LIMIT 5
        """, (key_id,))
        
        errors = await execute_query("""
            SELECT status_code, COUNT(*) as count
            FROM api_usage_logs
            WHERE api_key_id = %s 
              AND created_at > NOW() - INTERVAL '24 hours'
              AND status_code >= 400
            GROUP BY status_code
            ORDER BY count DESC
            LIMIT 3
        """, (key_id,))
        
        message = f"📊 {format_bold(await t_for_user('api.stats.title', user.id))}\n\n"
        message += f"{await t_for_user('api.stats.key_name', user.id, name=escape_html(key_name))}\n\n"
        
        if stats_24h and stats_24h[0]['total_requests']:
            stats = stats_24h[0]
            total = stats['total_requests']
            successful = stats['successful'] or 0
            success_rate = (successful / total * 100) if total > 0 else 0
            avg_time = int(stats['avg_response']) if stats['avg_response'] else 0
            
            message += f"📈 {await t_for_user('api.stats.last_24h', user.id)}\n"
            message += f"  • {await t_for_user('api.stats.total_requests', user.id, count=total)}\n"
            message += f"  • {await t_for_user('api.stats.successful', user.id, count=successful, percent=success_rate)}\n"
            message += f"  • {await t_for_user('api.stats.failed', user.id, count=total - successful)}\n"
            message += f"  • {await t_for_user('api.stats.avg_response', user.id, ms=avg_time)}\n\n"
            
            if top_endpoints:
                message += f"🔝 {await t_for_user('api.stats.top_endpoints', user.id)}\n"
                for idx, endpoint in enumerate(top_endpoints, 1):
                    message += f"  {await t_for_user('api.stats.endpoint_entry', user.id, index=idx, method=endpoint['method'], endpoint=endpoint['endpoint'], count=endpoint['count'])}\n"
                message += "\n"
            
            if errors:
                message += f"⚠️ {await t_for_user('api.stats.recent_errors', user.id)}\n"
                for error in errors:
                    message += f"  • {await t_for_user('api.stats.error_entry', user.id, code=error['status_code'], count=error['count'])}\n"
        else:
            message += f"{await t_for_user('api.stats.no_usage', user.id)}\n"
        
        keyboard = [[InlineKeyboardButton(await t_for_user('api.buttons.back', user.id), callback_data=f"api_manage_{key_id}")]]
        
        await query.edit_message_text(text=message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    
    except Exception as e:
        logger.error(f"Error showing API stats: {e}")
        await query.edit_message_text(text=await t_for_user('api.errors.stats_error', user.id))


async def confirm_api_key_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask for confirmation before revoking an API key."""
    query = update.callback_query
    await query.answer()
    
    key_id = int(query.data.split('_')[-1])
    
    try:
        user = update.effective_user
        internal_user_id = await get_internal_user_id_from_telegram_id(user.id)
        
        key_result = await execute_query("""
            SELECT name, created_at, last_used_at
            FROM api_keys
            WHERE id = %s AND user_id = %s AND is_active = true
        """, (key_id, internal_user_id))
        
        if not key_result:
            await query.edit_message_text(text=await t_for_user('api.errors.key_not_found', user.id))
            return
        
        key = key_result[0]
        
        message = f"⚠️ {format_bold(await t_for_user('api.revoke.confirm_title', user.id))}\n\n"
        message += f"{await t_for_user('api.revoke.confirm_prompt', user.id)}\n\n"
        message += f"🔑 {format_bold(escape_html(key['name']))}\n"
        message += f"   {await t_for_user('api.revoke.created', user.id, date=key['created_at'].strftime('%b %d, %Y'))}\n"
        
        if key['last_used_at']:
            last_used = key['last_used_at']
            now_utc = datetime.now(timezone.utc)
            if last_used.tzinfo is None:
                last_used = last_used.replace(tzinfo=timezone.utc)
            time_diff = now_utc - last_used
            if time_diff.days > 0:
                last_used_str = await t_for_user('api.dashboard.time_days_ago', user.id, days=time_diff.days)
            elif time_diff.seconds > 3600:
                last_used_str = await t_for_user('api.dashboard.time_hours_ago', user.id, hours=time_diff.seconds // 3600)
            else:
                last_used_str = await t_for_user('api.dashboard.time_minutes_ago', user.id, minutes=time_diff.seconds // 60)
            message += f"   {await t_for_user('api.revoke.last_used', user.id, time=last_used_str)}\n"
        
        message += f"\n⚠️ {await t_for_user('api.revoke.warning_title', user.id)}\n"
        message += f"{await t_for_user('api.revoke.warning_undone', user.id)}\n\n"
        message += f"{await t_for_user('api.revoke.warning_apps', user.id)}\n"
        
        keyboard = [
            [InlineKeyboardButton(await t_for_user('api.buttons.yes_revoke', user.id), callback_data=f"api_revoke_confirm_{key_id}")],
            [InlineKeyboardButton(await t_for_user('api.buttons.cancel', user.id), callback_data=f"api_manage_{key_id}")]
        ]
        
        await query.edit_message_text(text=message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    
    except Exception as e:
        logger.error(f"Error showing revoke confirmation: {e}")
        await query.edit_message_text(text=await t_for_user('api.errors.key_load_error', user.id))


async def revoke_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Revoke an API key permanently."""
    query = update.callback_query
    await query.answer()
    
    key_id = int(query.data.split('_')[-1])
    
    try:
        user = update.effective_user
        internal_user_id = await get_internal_user_id_from_telegram_id(user.id)
        
        key_result = await execute_query("""
            SELECT name FROM api_keys
            WHERE id = %s AND user_id = %s AND is_active = true
        """, (key_id, internal_user_id))
        
        if not key_result:
            await query.edit_message_text(text=await t_for_user('api.errors.key_not_found', user.id))
            return
        
        key_name = key_result[0]['name']
        
        await execute_update("""
            UPDATE api_keys
            SET is_active = false, revoked_at = CURRENT_TIMESTAMP,
                revoked_reason = 'Revoked by user via Telegram bot'
            WHERE id = %s AND user_id = %s
        """, (key_id, internal_user_id))
        
        message = f"✅ {format_bold(await t_for_user('api.revoke.success_title', user.id))}\n\n"
        message += f"{await t_for_user('api.revoke.success_message', user.id, name=escape_html(key_name))}\n\n"
        message += f"{await t_for_user('api.revoke.success_apps', user.id)}\n"
        
        keyboard = [[InlineKeyboardButton(await t_for_user('api.buttons.back_api', user.id), callback_data="api_management_main")]]
        
        await query.edit_message_text(text=message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
        logger.info(f"API key revoked: {key_name} (ID: {key_id}) by user {user.id}")
    
    except Exception as e:
        logger.error(f"Error revoking API key: {e}")
        await query.edit_message_text(text=await t_for_user('api.errors.revoke_error', user.id))


async def show_api_documentation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Direct users to the comprehensive developer portal."""
    query = update.callback_query
    if query:
        await query.answer()
    
    user = update.effective_user
    
    message = f"📚 {format_bold(await t_for_user('api.docs.title', user.id))}\n\n"
    message += f"🔗 <a href=\"https://developers.hostbay.io\">{await t_for_user('api.docs.url', user.id)}</a>\n\n"
    message += f"📖 {await t_for_user('api.docs.includes_title', user.id)}\n"
    message += f"• {await t_for_user('api.docs.full_reference', user.id)}\n"
    message += f"• {await t_for_user('api.docs.tutorials', user.id)}\n"
    message += f"• {await t_for_user('api.docs.languages', user.id)}\n"
    message += f"• {await t_for_user('api.docs.interactive', user.id)}\n"
    
    keyboard = [
        [InlineKeyboardButton(await t_for_user('api.buttons.open_portal', user.id), url="https://developers.hostbay.io")],
        [InlineKeyboardButton(await t_for_user('api.buttons.back', user.id), callback_data="api_management_main")]
    ]
    
    if query:
        await query.edit_message_text(text=message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)
    else:
        await update.message.reply_text(text=message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)
