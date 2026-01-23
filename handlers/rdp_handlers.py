"""
RDP Handlers - Windows RDP server management

Contains actual implementations for:
- RDP main menu
- RDP purchase flow
- Server management
"""

import logging
from typing import Optional, Dict, List, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.common import (
    safe_edit_message,
    get_region_name,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Imports helper
# ============================================================================

def _get_imports():
    """Lazy imports to avoid circular dependencies"""
    from localization import t, t_for_user
    from database import execute_query
    from unified_user_id_handlers import get_internal_user_id_from_telegram_id
    return t, t_for_user, execute_query, get_internal_user_id_from_telegram_id


async def get_user_lang_fast(user, context):
    """Get user language with caching"""
    from handlers.common import get_user_lang_fast as _get_user_lang_fast
    return await _get_user_lang_fast(user, context)


# ============================================================================
# RDP Main Interface (Implemented)
# ============================================================================

async def handle_rdp_main(query):
    """Show RDP main menu with features and options"""
    _, t_for_user, _, _ = _get_imports()
    
    try:
        user = query.from_user
        
        message = await t_for_user('rdp.main.title', user.id)
        message += "\n\n"
        message += await t_for_user('rdp.main.features', user.id)
        message += "\n"
        message += await t_for_user('rdp.main.description', user.id)
        message += "\n"
        message += await t_for_user('rdp.main.offerings', user.id)
        
        keyboard = [
            [InlineKeyboardButton(await t_for_user('rdp.buttons.purchase', user.id), callback_data="rdp_purchase_start")],
            [InlineKeyboardButton(await t_for_user('rdp.buttons.my_servers', user.id), callback_data="rdp_my_servers")],
            [InlineKeyboardButton(await t_for_user('rdp.buttons.back_main', user.id), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await safe_edit_message(query, message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error("Error in RDP main menu: %s", e)
        user = query.from_user
        await safe_edit_message(query, await t_for_user('rdp.errors.menu_error', user.id))


async def handle_rdp_purchase_start(query, context):
    """Two-path entry point for RDP purchase - Quick Deploy or Customize"""
    _, t_for_user, execute_query, get_internal_user_id_from_telegram_id = _get_imports()
    
    user = query.from_user
    try:
        logger.info("🚀 RDP purchase start - two-path entry for user %s", user.id)
        
        # Initialize wizard state
        context.user_data['rdp_wizard'] = {
            'template_id': None,
            'plan_id': None,
            'region': None,
            'billing_cycle': 'monthly'
        }
        
        # Get user ID and existing servers
        db_user_id = await get_internal_user_id_from_telegram_id(user.id)
        servers = []
        if db_user_id:
            servers = await execute_query("""
                SELECT id, hostname, status, plan_id, public_ip 
                FROM rdp_servers 
                WHERE user_id = %s AND deleted_at IS NULL 
                ORDER BY created_at DESC 
                LIMIT 3
            """, (db_user_id,))
        
        message = await t_for_user('rdp.purchase.title', user.id) + "\n\n"
        message += await t_for_user('rdp.purchase.features_short', user.id) + "\n"
        message += await t_for_user('rdp.purchase.description_short', user.id) + "\n\n"
        
        # Show existing servers if any
        if servers and len(servers) > 0:
            message += f"<b>{await t_for_user('rdp.purchase.your_servers', user.id)}</b>\n"
            for server in servers:
                status_emoji = "🟢" if server['status'] == 'active' else "🟡" if server['status'] == 'provisioning' else "⚪"
                ip = server['public_ip'] if server.get('public_ip') else await t_for_user('rdp.purchase.pending', user.id)
                message += f"{status_emoji} <code>{ip}</code>\n"
            message += "\n"
        
        message += f"<b>{await t_for_user('rdp.purchase.choose_method', user.id)}</b>\n\n"
        message += f"<b>{await t_for_user('rdp.purchase.quick_deploy_label', user.id)}</b> {await t_for_user('rdp.purchase.quick_deploy_desc', user.id)}\n"
        message += f"<b>{await t_for_user('rdp.purchase.customize_label', user.id)}</b> {await t_for_user('rdp.purchase.customize_desc', user.id)}"
        
        keyboard = [
            [InlineKeyboardButton(await t_for_user('rdp.buttons.quick_deploy', user.id), callback_data="rdp_quick_deploy")],
            [InlineKeyboardButton(await t_for_user('rdp.buttons.customize', user.id), callback_data="rdp_customize_start")]
        ]
        
        # Add "My Servers" button if user has servers
        if servers and len(servers) > 0:
            keyboard.append([InlineKeyboardButton(await t_for_user('rdp.buttons.view_all', user.id), callback_data="rdp_my_servers")])
        
        keyboard.append([InlineKeyboardButton(await t_for_user('rdp.buttons.back_main', user.id), callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await safe_edit_message(query, message, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error("Error in RDP purchase start: %s", e)
        await safe_edit_message(query, await t_for_user('rdp.errors.purchase_start_error', user.id))


async def handle_rdp_my_servers(query, context=None):
    """Show user's RDP servers with status and management options"""
    _, t_for_user, execute_query, get_internal_user_id_from_telegram_id = _get_imports()
    
    user = query.from_user
    
    try:
        db_user_id = await get_internal_user_id_from_telegram_id(user.id)
        
        if not db_user_id:
            message = await t_for_user('rdp.my_servers.no_account', user.id)
            keyboard = [[InlineKeyboardButton(await t_for_user('rdp.buttons.back_main', user.id), callback_data="rdp_main")]]
            await safe_edit_message(query, message, reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        servers = await execute_query("""
            SELECT id, hostname, status, plan_id, public_ip, region, 
                   created_at, billing_cycle, next_billing_date
            FROM rdp_servers 
            WHERE user_id = %s AND deleted_at IS NULL 
            ORDER BY created_at DESC
        """, (db_user_id,))
        
        if not servers:
            message = await t_for_user('rdp.my_servers.no_servers', user.id)
            keyboard = [
                [InlineKeyboardButton(await t_for_user('rdp.buttons.purchase', user.id), callback_data="rdp_purchase_start")],
                [InlineKeyboardButton(await t_for_user('rdp.buttons.back_main', user.id), callback_data="rdp_main")]
            ]
            await safe_edit_message(query, message, reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        message = await t_for_user('rdp.my_servers.title', user.id) + "\n\n"
        
        keyboard = []
        for server in servers:
            status = server['status']
            if status == 'active':
                status_emoji = "🟢"
            elif status == 'provisioning':
                status_emoji = "🟡"
            elif status == 'stopped':
                status_emoji = "🔴"
            else:
                status_emoji = "⚪"
            
            ip = server['public_ip'] or await t_for_user('rdp.my_servers.pending', user.id)
            region = get_region_name(server['region']) if server.get('region') else 'Unknown'
            
            message += f"{status_emoji} <code>{ip}</code>\n"
            message += f"   Region: {region}\n"
            message += f"   Status: {status.title()}\n\n"
            
            button_text = f"{status_emoji} {ip}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"rdp_server_{server['id']}")])
        
        keyboard.extend([
            [InlineKeyboardButton(await t_for_user('rdp.buttons.purchase', user.id), callback_data="rdp_purchase_start")],
            [InlineKeyboardButton(await t_for_user('rdp.buttons.back_main', user.id), callback_data="rdp_main")]
        ])
        
        await safe_edit_message(query, message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error("Error showing RDP servers: %s", e)
        await safe_edit_message(query, await t_for_user('rdp.errors.servers_error', user.id))


# ============================================================================
# RDP Configuration (Delegated)
# ============================================================================

async def handle_rdp_quick_deploy(query, context):
    """Handle quick deploy option"""
    from handlers_main import handle_rdp_quick_deploy as _handler
    return await _handler(query, context)


async def handle_rdp_customize_start(query, context):
    """Start customization flow"""
    from handlers_main import handle_rdp_customize_start as _handler
    return await _handler(query, context)


async def handle_rdp_select_plan(query, context, plan_id: str):
    """Handle plan selection"""
    from handlers_main import handle_rdp_select_plan as _handler
    return await _handler(query, context, plan_id)


async def handle_rdp_change_windows(query, context):
    """Handle Windows version change"""
    from handlers_main import handle_rdp_change_windows as _handler
    return await _handler(query, context)


async def handle_rdp_set_template(query, context, template_id: str):
    """Set Windows template"""
    from handlers_main import handle_rdp_set_template as _handler
    return await _handler(query, context, template_id)


async def handle_rdp_region_smart(query, context):
    """Show smart region selection"""
    from handlers_main import handle_rdp_region_smart as _handler
    return await _handler(query, context)


async def handle_rdp_regions_all(query, context):
    """Show all regions"""
    from handlers_main import handle_rdp_regions_all as _handler
    return await _handler(query, context)


async def handle_rdp_set_region(query, context, region_code: str):
    """Set server region"""
    from handlers_main import handle_rdp_set_region as _handler
    return await _handler(query, context, region_code)


async def handle_rdp_billing_confirm(query, context, billing_cycle: str):
    """Confirm billing cycle"""
    from handlers_main import handle_rdp_billing_confirm as _handler
    return await _handler(query, context, billing_cycle)


async def handle_rdp_change_billing(query, context, region_code: str):
    """Change billing cycle"""
    from handlers_main import handle_rdp_change_billing as _handler
    return await _handler(query, context, region_code)


# ============================================================================
# RDP Order & Payment (Delegated)
# ============================================================================

async def handle_rdp_compact_confirmation(query, context):
    """Show compact order confirmation"""
    from handlers_main import handle_rdp_compact_confirmation as _handler
    return await _handler(query, context)


async def handle_rdp_quick_confirm(query, context):
    """Quick order confirmation"""
    from handlers_main import handle_rdp_quick_confirm as _handler
    return await _handler(query, context)


async def handle_rdp_confirm_and_create_order(query, context):
    """Confirm and create RDP order"""
    from handlers_main import handle_rdp_confirm_and_create_order as _handler
    return await _handler(query, context)


async def handle_rdp_select_payment_method(query, context):
    """Select payment method"""
    from handlers_main import handle_rdp_select_payment_method as _handler
    return await _handler(query, context)


async def handle_rdp_pay_crypto(query, context):
    """Handle crypto payment"""
    from handlers_main import handle_rdp_pay_crypto as _handler
    return await _handler(query, context)


async def handle_rdp_pay_wallet(query, context):
    """Handle wallet payment"""
    from handlers_main import handle_rdp_pay_wallet as _handler
    return await _handler(query, context)


# ============================================================================
# RDP Server Management (Delegated)
# ============================================================================

async def handle_rdp_server_details(query, context, server_id: str):
    """Show server details"""
    from handlers_main import handle_rdp_server_details as _handler
    return await _handler(query, context, server_id)


async def handle_rdp_start_server(query, context, server_id: str):
    """Start RDP server"""
    from handlers_main import handle_rdp_start_server as _handler
    return await _handler(query, context, server_id)


async def handle_rdp_stop_server(query, context, server_id: str):
    """Stop RDP server"""
    from handlers_main import handle_rdp_stop_server as _handler
    return await _handler(query, context, server_id)


async def handle_rdp_restart_server(query, context, server_id: str):
    """Restart RDP server"""
    from handlers_main import handle_rdp_restart_server as _handler
    return await _handler(query, context, server_id)


async def handle_rdp_reinstall_confirm(query, context, server_id: str):
    """Confirm server reinstall"""
    from handlers_main import handle_rdp_reinstall_confirm as _handler
    return await _handler(query, context, server_id)


async def handle_rdp_reinstall(query, context, server_id: str):
    """Reinstall RDP server"""
    from handlers_main import handle_rdp_reinstall as _handler
    return await _handler(query, context, server_id)


async def handle_rdp_delete_confirm(query, context, server_id: str):
    """Confirm server deletion"""
    from handlers_main import handle_rdp_delete_confirm as _handler
    return await _handler(query, context, server_id)


async def handle_rdp_delete(query, context, server_id: str):
    """Delete RDP server"""
    from handlers_main import handle_rdp_delete as _handler
    return await _handler(query, context, server_id)


# ============================================================================
# RDP Provisioning (Delegated)
# ============================================================================

async def provision_rdp_server(telegram_id: int, order_id: int, metadata: dict):
    """Provision RDP server"""
    from handlers_main import provision_rdp_server as _handler
    return await _handler(telegram_id, order_id, metadata)


async def wait_for_reinstall_complete(telegram_id: int, server_id: int, instance_id: str):
    """Wait for reinstall to complete"""
    from handlers_main import wait_for_reinstall_complete as _handler
    return await _handler(telegram_id, server_id, instance_id)


# ============================================================================
# Helper Functions
# ============================================================================

def get_rdp_default(key):
    """Get RDP default value"""
    defaults = {
        'template_id': '2379',  # Windows Server 2022
        'plan_id': 'vc2-1c-1gb',
        'region': 'ewr',
        'billing_cycle': 'monthly'
    }
    return defaults.get(key)
