"""
RDP Handlers - Windows RDP server management

Handles:
- RDP server purchase flow
- Server deployment and provisioning
- Server management (start, stop, restart)
- Server reinstallation and deletion
- Payment processing for RDP
"""

import logging
from typing import Optional, Dict, List, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.common import (
    safe_edit_message,
    get_user_lang_fast,
    get_region_name,
)

logger = logging.getLogger(__name__)


# ============================================================================
# RDP Main Interface
# ============================================================================

async def handle_rdp_main(query):
    """Show main RDP interface"""
    from handlers import handle_rdp_main as _handler
    return await _handler(query)


async def handle_rdp_purchase_start(query, context):
    """Start RDP purchase flow"""
    from handlers import handle_rdp_purchase_start as _handler
    return await _handler(query, context)


async def handle_rdp_quick_deploy(query, context):
    """Handle quick deploy option"""
    from handlers import handle_rdp_quick_deploy as _handler
    return await _handler(query, context)


async def handle_rdp_customize_start(query, context):
    """Start customization flow"""
    from handlers import handle_rdp_customize_start as _handler
    return await _handler(query, context)


# ============================================================================
# RDP Configuration
# ============================================================================

async def handle_rdp_select_plan(query, context, plan_id: str):
    """Handle plan selection"""
    from handlers import handle_rdp_select_plan as _handler
    return await _handler(query, context, plan_id)


async def handle_rdp_change_windows(query, context):
    """Handle Windows version change"""
    from handlers import handle_rdp_change_windows as _handler
    return await _handler(query, context)


async def handle_rdp_set_template(query, context, template_id: str):
    """Set Windows template"""
    from handlers import handle_rdp_set_template as _handler
    return await _handler(query, context, template_id)


async def handle_rdp_region_smart(query, context):
    """Show smart region selection"""
    from handlers import handle_rdp_region_smart as _handler
    return await _handler(query, context)


async def handle_rdp_regions_all(query, context):
    """Show all regions"""
    from handlers import handle_rdp_regions_all as _handler
    return await _handler(query, context)


async def handle_rdp_set_region(query, context, region_code: str):
    """Set server region"""
    from handlers import handle_rdp_set_region as _handler
    return await _handler(query, context, region_code)


async def handle_rdp_billing_confirm(query, context, billing_cycle: str):
    """Confirm billing cycle"""
    from handlers import handle_rdp_billing_confirm as _handler
    return await _handler(query, context, billing_cycle)


async def handle_rdp_change_billing(query, context, region_code: str):
    """Change billing cycle"""
    from handlers import handle_rdp_change_billing as _handler
    return await _handler(query, context, region_code)


# ============================================================================
# RDP Order & Payment
# ============================================================================

async def handle_rdp_compact_confirmation(query, context):
    """Show compact order confirmation"""
    from handlers import handle_rdp_compact_confirmation as _handler
    return await _handler(query, context)


async def handle_rdp_quick_confirm(query, context):
    """Quick order confirmation"""
    from handlers import handle_rdp_quick_confirm as _handler
    return await _handler(query, context)


async def handle_rdp_confirm_and_create_order(query, context):
    """Confirm and create RDP order"""
    from handlers import handle_rdp_confirm_and_create_order as _handler
    return await _handler(query, context)


async def handle_rdp_select_payment_method(query, context):
    """Select payment method"""
    from handlers import handle_rdp_select_payment_method as _handler
    return await _handler(query, context)


async def handle_rdp_pay_crypto(query, context):
    """Handle crypto payment"""
    from handlers import handle_rdp_pay_crypto as _handler
    return await _handler(query, context)


async def handle_rdp_crypto_currency(query, context, currency: str):
    """Handle crypto currency selection"""
    from handlers import handle_rdp_crypto_currency as _handler
    return await _handler(query, context, currency)


async def handle_rdp_crypto_from_qr(query, context, order_uuid: str):
    """Handle crypto payment from QR"""
    from handlers import handle_rdp_crypto_from_qr as _handler
    return await _handler(query, context, order_uuid)


async def handle_rdp_payment_back(query, context, order_uuid: str):
    """Go back from payment"""
    from handlers import handle_rdp_payment_back as _handler
    return await _handler(query, context, order_uuid)


async def handle_rdp_cancel_order(query, context, order_uuid: str):
    """Cancel RDP order"""
    from handlers import handle_rdp_cancel_order as _handler
    return await _handler(query, context, order_uuid)


async def handle_rdp_pay_wallet(query, context):
    """Handle wallet payment"""
    from handlers import handle_rdp_pay_wallet as _handler
    return await _handler(query, context)


# ============================================================================
# RDP Provisioning
# ============================================================================

async def provision_rdp_server(telegram_id: int, order_id: int, metadata: dict):
    """Provision RDP server"""
    from handlers import provision_rdp_server as _handler
    return await _handler(telegram_id, order_id, metadata)


async def wait_for_reinstall_complete(telegram_id: int, server_id: int, instance_id: str):
    """Wait for reinstall to complete"""
    from handlers import wait_for_reinstall_complete as _handler
    return await _handler(telegram_id, server_id, instance_id)


# ============================================================================
# RDP Server Management
# ============================================================================

async def handle_rdp_my_servers(query, context=None):
    """Show user's RDP servers"""
    from handlers import handle_rdp_my_servers as _handler
    return await _handler(query, context)


async def handle_rdp_server_details(query, context, server_id: str):
    """Show server details"""
    from handlers import handle_rdp_server_details as _handler
    return await _handler(query, context, server_id)


async def handle_rdp_start_server(query, context, server_id: str):
    """Start RDP server"""
    from handlers import handle_rdp_start_server as _handler
    return await _handler(query, context, server_id)


async def handle_rdp_stop_server(query, context, server_id: str):
    """Stop RDP server"""
    from handlers import handle_rdp_stop_server as _handler
    return await _handler(query, context, server_id)


async def handle_rdp_restart_server(query, context, server_id: str):
    """Restart RDP server"""
    from handlers import handle_rdp_restart_server as _handler
    return await _handler(query, context, server_id)


async def handle_rdp_reinstall_confirm(query, context, server_id: str):
    """Confirm server reinstall"""
    from handlers import handle_rdp_reinstall_confirm as _handler
    return await _handler(query, context, server_id)


async def handle_rdp_reinstall(query, context, server_id: str):
    """Reinstall RDP server"""
    from handlers import handle_rdp_reinstall as _handler
    return await _handler(query, context, server_id)


async def handle_rdp_delete_confirm(query, context, server_id: str):
    """Confirm server deletion"""
    from handlers import handle_rdp_delete_confirm as _handler
    return await _handler(query, context, server_id)


async def handle_rdp_delete(query, context, server_id: str):
    """Delete RDP server"""
    from handlers import handle_rdp_delete as _handler
    return await _handler(query, context, server_id)


# ============================================================================
# Legacy Selection Handlers
# ============================================================================

async def handle_rdp_template_selection(query, context, template_id: str):
    """Handle template selection (legacy)"""
    from handlers import handle_rdp_template_selection as _handler
    return await _handler(query, context, template_id)


async def handle_rdp_plan_selection(query, context, plan_id: str):
    """Handle plan selection (legacy)"""
    from handlers import handle_rdp_plan_selection as _handler
    return await _handler(query, context, plan_id)


async def handle_rdp_region_selection(query, context, region_id: str):
    """Handle region selection (legacy)"""
    from handlers import handle_rdp_region_selection as _handler
    return await _handler(query, context, region_id)


async def handle_rdp_billing_selection(query, context, billing_cycle: str):
    """Handle billing selection (legacy)"""
    from handlers import handle_rdp_billing_selection as _handler
    return await _handler(query, context, billing_cycle)


# ============================================================================
# Helper Functions
# ============================================================================

def get_rdp_default(key):
    """Get RDP default value"""
    from handlers import get_rdp_default as _func
    return _func(key)
