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
from typing import Optional, Dict, List, Any, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.common import (
    safe_edit_message,
    escape_content_for_display,
    escape_html,
    get_user_lang_fast,
    smart_dns_callback,
    create_short_dns_callback,
    is_ip_proxyable,
    clear_dns_wizard_state,
    clear_dns_wizard_custom_subdomain_state,
    clear_all_dns_wizard_state,
    get_wizard_state,
    set_wizard_state,
)

logger = logging.getLogger(__name__)


# ============================================================================
# DNS Dashboard & Record Display
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


# ============================================================================
# DNS Wizard - Record Type Selection
# ============================================================================

async def show_dns_add_record_menu(query, domain: str, context):
    """Show DNS record type selection menu"""
    from handlers_main import show_dns_add_record_menu as _handler
    return await _handler(query, domain, context)


async def handle_dns_wizard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle DNS wizard callback interactions"""
    from handlers_main import handle_dns_wizard_callback as _handler
    return await _handler(update, context)


# ============================================================================
# A Record Wizard
# ============================================================================

async def continue_a_record_wizard(query, context, wizard_state: Dict):
    """Continue A record creation wizard"""
    from handlers_main import continue_a_record_wizard as _handler
    return await _handler(query, context, wizard_state)


async def show_a_record_confirmation(query, wizard_state: Dict):
    """Show A record creation confirmation"""
    from handlers_main import show_a_record_confirmation as _handler
    return await _handler(query, wizard_state)


async def handle_dns_wizard_ip_input(update, context, ip_address: str, wizard_state: Dict):
    """Handle IP address input for A record"""
    from handlers_main import handle_dns_wizard_ip_input as _handler
    return await _handler(update, context, ip_address, wizard_state)


# ============================================================================
# CNAME Record Wizard
# ============================================================================

async def continue_cname_record_wizard(query, context, wizard_state: Dict):
    """Continue CNAME record creation wizard"""
    from handlers_main import continue_cname_record_wizard as _handler
    return await _handler(query, context, wizard_state)


async def show_cname_record_confirmation(query, wizard_state: Dict):
    """Show CNAME record creation confirmation"""
    from handlers_main import show_cname_record_confirmation as _handler
    return await _handler(query, wizard_state)


async def handle_dns_wizard_cname_input(update, context, target: str, wizard_state: Dict):
    """Handle CNAME target input"""
    from handlers_main import handle_dns_wizard_cname_input as _handler
    return await _handler(update, context, target, wizard_state)


# ============================================================================
# TXT Record Wizard
# ============================================================================

async def continue_txt_record_wizard(query, context, wizard_state: Dict):
    """Continue TXT record creation wizard"""
    from handlers_main import continue_txt_record_wizard as _handler
    return await _handler(query, context, wizard_state)


async def show_txt_record_confirmation(query, wizard_state: Dict):
    """Show TXT record creation confirmation"""
    from handlers_main import show_txt_record_confirmation as _handler
    return await _handler(query, wizard_state)


async def handle_dns_wizard_txt_input(update, context, content: str, wizard_state: Dict):
    """Handle TXT content input"""
    from handlers_main import handle_dns_wizard_txt_input as _handler
    return await _handler(update, context, content, wizard_state)


# ============================================================================
# MX Record Wizard
# ============================================================================

async def continue_mx_record_wizard(query, context, wizard_state: Dict):
    """Continue MX record creation wizard"""
    from handlers_main import continue_mx_record_wizard as _handler
    return await _handler(query, context, wizard_state)


async def show_mx_record_confirmation(query, wizard_state: Dict):
    """Show MX record creation confirmation"""
    from handlers_main import show_mx_record_confirmation as _handler
    return await _handler(query, wizard_state)


async def handle_dns_wizard_mx_input(update, context, server: str, wizard_state: Dict):
    """Handle MX server input"""
    from handlers_main import handle_dns_wizard_mx_input as _handler
    return await _handler(update, context, server, wizard_state)


# ============================================================================
# DNS Record Creation
# ============================================================================

async def create_dns_record_from_wizard(query, context, wizard_state: Dict):
    """Create DNS record using wizard state"""
    from handlers_main import create_dns_record_from_wizard as _handler
    return await _handler(query, context, wizard_state)


# ============================================================================
# DNS Record Editing
# ============================================================================

async def show_dns_record_edit(query, domain: str, record_id: str, context):
    """Show DNS record edit interface"""
    from handlers_main import show_dns_record_edit as _handler
    return await _handler(query, domain, record_id, context)


async def handle_dns_record_edit_callback(query, context, domain: str, record_type: str, field: str, record_id: str):
    """Handle DNS record edit callback"""
    from handlers_main import handle_dns_record_edit_callback as _handler
    return await _handler(query, context, domain, record_type, field, record_id)


async def save_dns_record_changes(query, context, domain: str, record_type: str, record_id: str):
    """Save DNS record changes"""
    from handlers_main import save_dns_record_changes as _handler
    return await _handler(query, context, domain, record_type, record_id)


# ============================================================================
# DNS Record Deletion
# ============================================================================

async def confirm_dns_record_delete(query, domain: str, record_id: str, context):
    """Confirm DNS record deletion"""
    from handlers_main import confirm_dns_record_delete as _handler
    return await _handler(query, domain, record_id, context)


async def delete_dns_record(query, domain: str, record_id: str, context):
    """Delete DNS record"""
    from handlers_main import delete_dns_record as _handler
    return await _handler(query, domain, record_id, context)


# ============================================================================
# Nameserver Management
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


async def show_custom_nameserver_form(query, context, domain_name: str):
    """Show custom nameserver form"""
    from handlers_main import show_custom_nameserver_form as _handler
    return await _handler(query, context, domain_name)


async def handle_nameserver_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, nameserver_input_context):
    """Handle nameserver text input"""
    from handlers_main import handle_nameserver_input as _handler
    return await _handler(update, context, text, nameserver_input_context)


async def execute_nameserver_update(query, context, domain_name: str, ns_data_token: str):
    """Execute nameserver update"""
    from handlers_main import execute_nameserver_update as _handler
    return await _handler(query, context, domain_name, ns_data_token)


# ============================================================================
# Security Settings
# ============================================================================

async def show_security_settings(query, domain_name: str):
    """Show domain security settings"""
    from handlers_main import show_security_settings as _handler
    return await _handler(query, domain_name)


async def toggle_javascript_challenge(query, domain_name: str, action: str):
    """Toggle JavaScript challenge setting"""
    from handlers_main import toggle_javascript_challenge as _handler
    return await _handler(query, domain_name, action)


async def toggle_force_https_setting(query, domain_name: str, action: str):
    """Toggle force HTTPS setting"""
    from handlers_main import toggle_force_https_setting as _handler
    return await _handler(query, domain_name, action)


async def toggle_auto_proxy_setting(query, domain_name: str, action: str):
    """Toggle auto proxy setting"""
    from handlers_main import toggle_auto_proxy_setting as _handler
    return await _handler(query, domain_name, action)


# ============================================================================
# Helper Functions
# ============================================================================

async def get_available_names_for_record_type(domain: str, record_type: str, zone_id: str) -> List[Dict]:
    """Get available subdomain names for a record type"""
    from handlers_main import get_available_names_for_record_type as _handler
    return await _handler(domain, record_type, zone_id)


def validate_dns_record_field(record_type: str, field: str, value: str, user_lang: str = 'en') -> Dict[str, Any]:
    """Validate DNS record field value"""
    from handlers_main import validate_dns_record_field as _func
    return _func(record_type, field, value, user_lang)


def get_proxy_restriction_message(ip_str: str, user_lang: str = 'en') -> str:
    """Get proxy restriction message for IP"""
    from handlers_main import get_proxy_restriction_message as _func
    return _func(ip_str, user_lang)


async def analyze_domain_nameservers(domain_name: str) -> dict:
    """Analyze domain nameservers"""
    from handlers_main import analyze_domain_nameservers as _handler
    return await _handler(domain_name)


def detect_nameserver_provider(nameservers: list) -> str:
    """Detect nameserver provider"""
    from handlers_main import detect_nameserver_provider as _func
    return _func(nameservers)
