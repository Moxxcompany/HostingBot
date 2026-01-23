"""
Callback Router - Centralized callback routing with modular handler delegation

This module provides a cleaner callback routing system by organizing
callbacks into functional groups and delegating to appropriate handler modules.
"""

import logging
from typing import Callable, Dict, List, Optional, Tuple, Any
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


# Type aliases
CallbackHandler = Callable[[Any, Any], Any]  # (query, context) -> awaitable
PrefixHandler = Callable[[Any, Any, str], Any]  # (query, context, param) -> awaitable


class CallbackRouter:
    """
    Modular callback router that organizes callbacks by functional domain.
    
    Usage:
        router = CallbackRouter()
        router.register_exact("main_menu", show_main_menu)
        router.register_prefix("dns:", handle_dns_callback)
        
        # In handle_callback:
        if await router.route(data, query, context):
            return  # Handled
    """
    
    def __init__(self):
        self._exact_routes: Dict[str, CallbackHandler] = {}
        self._prefix_routes: List[Tuple[str, PrefixHandler]] = []
        self._startswith_routes: List[Tuple[str, CallbackHandler]] = []
        
    def register_exact(self, callback_data: str, handler: CallbackHandler) -> None:
        """Register handler for exact callback_data match"""
        self._exact_routes[callback_data] = handler
        
    def register_prefix(self, prefix: str, handler: PrefixHandler) -> None:
        """Register handler for prefix match (extracts parameter after prefix)"""
        self._prefix_routes.append((prefix, handler))
        # Sort by length descending to match longer prefixes first
        self._prefix_routes.sort(key=lambda x: len(x[0]), reverse=True)
        
    def register_startswith(self, prefix: str, handler: CallbackHandler) -> None:
        """Register handler for startswith match (passes full data)"""
        self._startswith_routes.append((prefix, handler))
        self._startswith_routes.sort(key=lambda x: len(x[0]), reverse=True)
        
    async def route(self, data: str, query, context) -> bool:
        """
        Route callback to appropriate handler.
        
        Returns True if handled, False if no matching route found.
        """
        # Check exact matches first
        if data in self._exact_routes:
            logger.info(f"Router: exact match '{data}'")
            await self._exact_routes[data](query, context)
            return True
            
        # Check prefix matches (extracts parameter)
        for prefix, handler in self._prefix_routes:
            if data.startswith(prefix):
                param = data[len(prefix):]
                logger.info(f"Router: prefix '{prefix}' with param '{param}'")
                await handler(query, context, param)
                return True
                
        # Check startswith matches (passes full data)
        for prefix, handler in self._startswith_routes:
            if data.startswith(prefix):
                logger.info(f"Router: startswith '{prefix}'")
                await handler(query, context)
                return True
                
        return False


# ============================================================================
# Route Definitions - Organized by Domain
# ============================================================================

def create_core_routes(router: CallbackRouter) -> None:
    """Register core navigation routes"""
    from handlers.core_handlers import (
        show_personalized_dashboard, show_profile_interface,
        show_contact_support, show_reseller_info
    )
    from handlers.domain_handlers import (
        show_search_interface, show_user_domains_complete
    )
    from handlers.payment_handlers import show_wallet_interface
    from admin_handlers import clear_admin_states
    
    async def main_menu_handler(query, context):
        clear_admin_states(context)
        from handlers_main import show_personalized_dashboard
        await show_personalized_dashboard(query)
    
    async def search_domains_handler(query, context):
        clear_admin_states(context)
        from handlers_main import show_search_interface
        await show_search_interface(query)
    
    async def my_domains_handler(query, context):
        clear_admin_states(context)
        from handlers_main import show_user_domains_complete
        await show_user_domains_complete(query, context)
    
    async def wallet_handler(query, context):
        clear_admin_states(context)
        from handlers_main import show_wallet_interface
        await show_wallet_interface(query, context)
    
    async def profile_handler(query, context):
        clear_admin_states(context)
        from handlers_main import show_profile_interface
        await show_profile_interface(query)
    
    async def reseller_handler(query, context):
        from handlers_main import show_reseller_info
        await show_reseller_info(query)
    
    async def contact_handler(query, context):
        from handlers_main import show_contact_support
        await show_contact_support(query)
    
    router.register_exact("main_menu", main_menu_handler)
    router.register_exact("search_domains", search_domains_handler)
    router.register_exact("my_domains", my_domains_handler)
    router.register_exact("wallet_main", wallet_handler)
    router.register_exact("profile_main", profile_handler)
    router.register_exact("reseller_program", reseller_handler)
    router.register_exact("contact_support", contact_handler)


def create_hosting_routes(router: CallbackRouter) -> None:
    """Register hosting management routes"""
    from admin_handlers import clear_admin_states
    
    async def hosting_main_handler(query, context):
        clear_admin_states(context)
        from handlers.hosting_handlers import show_hosting_interface
        await show_hosting_interface(query, context)
    
    async def manage_hosting_handler(query, context, subscription_id: str):
        from handlers.hosting_handlers import show_hosting_management
        await show_hosting_management(query, subscription_id)
    
    async def hosting_details_handler(query, context, subscription_id: str):
        from handlers.hosting_handlers import show_hosting_details
        await show_hosting_details(query, subscription_id)
    
    async def cpanel_login_handler(query, context, subscription_id: str):
        from handlers.hosting_handlers import show_cpanel_login
        await show_cpanel_login(query, subscription_id)
    
    async def hosting_usage_handler(query, context, subscription_id: str):
        from handlers.hosting_handlers import show_hosting_usage
        await show_hosting_usage(query, subscription_id)
    
    async def suspend_hosting_handler(query, context, subscription_id: str):
        from handlers.hosting_handlers import suspend_hosting_account
        await suspend_hosting_account(query, subscription_id)
    
    async def unsuspend_hosting_handler(query, context, subscription_id: str):
        from handlers_main import unsuspend_hosting_account
        await unsuspend_hosting_account(query, subscription_id)
    
    async def confirm_suspend_handler(query, context, subscription_id: str):
        from handlers_main import confirm_hosting_suspension
        await confirm_hosting_suspension(query, subscription_id)
    
    async def cancel_suspend_handler(query, context, subscription_id: str):
        from handlers.hosting_handlers import show_hosting_management
        await show_hosting_management(query, subscription_id)
    
    async def restart_hosting_handler(query, context, subscription_id: str):
        from handlers_main import restart_hosting_services
        await restart_hosting_services(query, subscription_id)
    
    async def check_status_handler(query, context, subscription_id: str):
        from handlers_main import check_hosting_status
        await check_hosting_status(query, subscription_id)
    
    async def renew_suspended_handler(query, context, subscription_id: str):
        from handlers.hosting_handlers import handle_renew_suspended_hosting
        await handle_renew_suspended_hosting(query, subscription_id)
    
    async def renew_wallet_handler(query, context, subscription_id: str):
        from handlers_main import process_manual_renewal_wallet
        await process_manual_renewal_wallet(query, subscription_id)
    
    async def renew_crypto_handler(query, context, subscription_id: str):
        from handlers_main import process_manual_renewal_crypto
        await process_manual_renewal_crypto(query, subscription_id)
    
    async def insufficient_funds_handler(query, context, subscription_id: str):
        from handlers_main import show_insufficient_funds_message
        await show_insufficient_funds_message(query, subscription_id)
    
    router.register_exact("hosting_main", hosting_main_handler)
    router.register_prefix("manage_hosting_", manage_hosting_handler)
    router.register_prefix("hosting_details_", hosting_details_handler)
    router.register_prefix("cpanel_login_", cpanel_login_handler)
    router.register_prefix("hosting_usage_", hosting_usage_handler)
    router.register_prefix("suspend_hosting_", suspend_hosting_handler)
    router.register_prefix("unsuspend_hosting_", unsuspend_hosting_handler)
    router.register_prefix("confirm_suspend_", confirm_suspend_handler)
    router.register_prefix("cancel_suspend_", cancel_suspend_handler)
    router.register_prefix("restart_hosting_", restart_hosting_handler)
    router.register_prefix("check_hosting_status_", check_status_handler)
    router.register_prefix("renew_suspended_", renew_suspended_handler)
    router.register_prefix("renew_wallet_", renew_wallet_handler)
    router.register_prefix("renew_crypto_", renew_crypto_handler)
    router.register_prefix("insufficient_funds_", insufficient_funds_handler)


def create_rdp_routes(router: CallbackRouter) -> None:
    """Register RDP server management routes"""
    
    async def rdp_main_handler(query, context):
        from handlers.rdp_handlers import handle_rdp_main
        await handle_rdp_main(query)
    
    async def rdp_purchase_handler(query, context):
        from handlers.rdp_handlers import handle_rdp_purchase_start
        await handle_rdp_purchase_start(query, context)
    
    async def rdp_my_servers_handler(query, context):
        from handlers.rdp_handlers import handle_rdp_my_servers
        await handle_rdp_my_servers(query, context)
    
    async def rdp_quick_deploy_handler(query, context):
        from handlers_main import handle_rdp_quick_deploy
        await handle_rdp_quick_deploy(query, context)
    
    async def rdp_quick_confirm_handler(query, context):
        from handlers_main import handle_rdp_quick_confirm
        await handle_rdp_quick_confirm(query, context)
    
    async def rdp_customize_handler(query, context):
        from handlers_main import handle_rdp_customize_start
        await handle_rdp_customize_start(query, context)
    
    async def rdp_change_windows_handler(query, context):
        from handlers_main import handle_rdp_change_windows
        await handle_rdp_change_windows(query, context)
    
    async def rdp_region_smart_handler(query, context):
        from handlers_main import handle_rdp_region_smart
        await handle_rdp_region_smart(query, context)
    
    async def rdp_regions_all_handler(query, context):
        from handlers_main import handle_rdp_regions_all
        await handle_rdp_regions_all(query, context)
    
    async def rdp_confirm_order_handler(query, context):
        from handlers_main import handle_rdp_confirm_and_create_order
        await handle_rdp_confirm_and_create_order(query, context)
    
    async def rdp_select_payment_handler(query, context):
        from handlers_main import handle_rdp_select_payment_method
        await handle_rdp_select_payment_method(query, context)
    
    async def rdp_pay_wallet_handler(query, context):
        from handlers_main import handle_rdp_pay_wallet
        await handle_rdp_pay_wallet(query, context)
    
    async def rdp_pay_crypto_handler(query, context):
        from handlers_main import handle_rdp_pay_crypto
        await handle_rdp_pay_crypto(query, context)
    
    # Prefix handlers
    async def rdp_select_plan_handler(query, context, plan_id: str):
        from handlers_main import handle_rdp_select_plan
        await handle_rdp_select_plan(query, context, plan_id)
    
    async def rdp_set_template_handler(query, context, template_id: str):
        from handlers_main import handle_rdp_set_template
        await handle_rdp_set_template(query, context, template_id)
    
    async def rdp_set_region_handler(query, context, region_code: str):
        from handlers_main import handle_rdp_set_region
        await handle_rdp_set_region(query, context, region_code)
    
    async def rdp_change_billing_handler(query, context, region_code: str):
        from handlers_main import handle_rdp_change_billing
        await handle_rdp_change_billing(query, context, region_code)
    
    async def rdp_server_handler(query, context, server_id: str):
        from handlers_main import handle_rdp_server_details
        await handle_rdp_server_details(query, context, server_id)
    
    async def rdp_start_handler(query, context, server_id: str):
        from handlers_main import handle_rdp_start_server
        await handle_rdp_start_server(query, context, server_id)
    
    async def rdp_stop_handler(query, context, server_id: str):
        from handlers_main import handle_rdp_stop_server
        await handle_rdp_stop_server(query, context, server_id)
    
    async def rdp_restart_handler(query, context, server_id: str):
        from handlers_main import handle_rdp_restart_server
        await handle_rdp_restart_server(query, context, server_id)
    
    async def rdp_crypto_handler(query, context, currency: str):
        from handlers_main import handle_rdp_crypto_currency
        await handle_rdp_crypto_currency(query, context, currency)
    
    async def rdp_cancel_order_handler(query, context, order_uuid: str):
        from handlers_main import handle_rdp_cancel_order
        await handle_rdp_cancel_order(query, context, order_uuid)
    
    async def rdp_payment_back_handler(query, context, order_uuid: str):
        from handlers_main import handle_rdp_payment_back
        await handle_rdp_payment_back(query, context, order_uuid)
    
    # Register exact routes
    router.register_exact("rdp_main", rdp_main_handler)
    router.register_exact("rdp_purchase_start", rdp_purchase_handler)
    router.register_exact("rdp_my_servers", rdp_my_servers_handler)
    router.register_exact("rdp_quick_deploy", rdp_quick_deploy_handler)
    router.register_exact("rdp_quick_confirm", rdp_quick_confirm_handler)
    router.register_exact("rdp_customize_start", rdp_customize_handler)
    router.register_exact("rdp_change_windows", rdp_change_windows_handler)
    router.register_exact("rdp_region_smart", rdp_region_smart_handler)
    router.register_exact("rdp_regions_all", rdp_regions_all_handler)
    router.register_exact("rdp_confirm_and_create_order", rdp_confirm_order_handler)
    router.register_exact("rdp_select_payment_method", rdp_select_payment_handler)
    router.register_exact("rdp_pay_wallet", rdp_pay_wallet_handler)
    router.register_exact("rdp_pay_crypto", rdp_pay_crypto_handler)
    
    # Register prefix routes
    router.register_prefix("rdp_select_plan_", rdp_select_plan_handler)
    router.register_prefix("rdp_set_template_", rdp_set_template_handler)
    router.register_prefix("rdp_set_region_", rdp_set_region_handler)
    router.register_prefix("rdp_change_billing_", rdp_change_billing_handler)
    router.register_prefix("rdp_crypto_", rdp_crypto_handler)
    router.register_prefix("rdp_cancel_order:", rdp_cancel_order_handler)
    router.register_prefix("rdp_payment_back:", rdp_payment_back_handler)
    router.register_prefix("rdp_start_", rdp_start_handler)
    router.register_prefix("rdp_stop_", rdp_stop_handler)
    router.register_prefix("rdp_restart_", rdp_restart_handler)
    router.register_prefix("rdp_server_", rdp_server_handler)


def create_dns_routes(router: CallbackRouter) -> None:
    """Register DNS management routes"""
    
    async def dns_callback_handler(query, context, data: str):
        from handlers_main import handle_dns_callback
        await handle_dns_callback(query, context, f"dns:{data}")
    
    async def dns_nav_handler(query, context):
        from handlers_main import handle_dns_nav_callback
        await handle_dns_nav_callback(query, context, query.data)
    
    async def dns_wizard_handler(query, context):
        from handlers_main import handle_dns_wizard_callback
        await handle_dns_wizard_callback(query, context, query.data)
    
    async def dns_edit_handler(query, context):
        from handlers_main import handle_dns_edit_callback
        await handle_dns_edit_callback(query, context, query.data)
    
    async def dns_delete_handler(query, context):
        from handlers_main import handle_delete_callback
        await handle_delete_callback(query, context, query.data)
    
    async def dns_domain_handler(query, context, domain_name: str):
        from handlers_main import handle_dns_callback
        from admin_handlers import clear_admin_states
        clear_admin_states(context)
        await handle_dns_callback(query, context, f"dns:{domain_name}:view")
    
    # DNS callbacks are complex - register startswith handlers
    router.register_startswith("dns_nav:", dns_nav_handler)
    router.register_startswith("dns_wizard:", dns_wizard_handler)
    router.register_startswith("dns_edit:", dns_edit_handler)
    router.register_startswith("dns_delete:", dns_delete_handler)
    router.register_prefix("dns:", dns_callback_handler)


def create_language_routes(router: CallbackRouter) -> None:
    """Register language selection routes"""
    from telegram import Update
    
    async def language_selection_handler(query, context):
        from handlers.core_handlers import show_language_selection
        mock_update = Update(update_id=0, callback_query=query)
        await show_language_selection(mock_update, context)
    
    async def language_from_profile_handler(query, context):
        from handlers.core_handlers import show_language_selection_from_profile
        mock_update = Update(update_id=0, callback_query=query)
        await show_language_selection_from_profile(mock_update, context)
    
    async def handle_lang_select_profile(query, context, lang_code: str):
        from handlers.core_handlers import handle_language_selection_from_profile
        mock_update = Update(update_id=0, callback_query=query)
        await handle_language_selection_from_profile(mock_update, context)
    
    async def handle_lang_select(query, context, lang_code: str):
        from handlers.core_handlers import handle_language_selection
        mock_update = Update(update_id=0, callback_query=query)
        await handle_language_selection(mock_update, context)
    
    router.register_exact("language_selection", language_selection_handler)
    router.register_exact("language_selection_from_profile", language_from_profile_handler)
    router.register_prefix("language_select_from_profile_", handle_lang_select_profile)
    router.register_prefix("language_select_", handle_lang_select)


def create_admin_routes(router: CallbackRouter) -> None:
    """Register admin management routes"""
    
    async def admin_broadcast_handler(query, context):
        from admin_handlers import handle_admin_broadcast
        await handle_admin_broadcast(query, context)
    
    async def admin_credit_handler(query, context):
        from admin_handlers import handle_admin_credit_wallet
        from telegram import Update
        mock_update = Update(update_id=0, callback_query=query)
        await handle_admin_credit_wallet(mock_update, context)
    
    async def admin_op_accounts_handler(query, context):
        from handlers.core_handlers import show_openprovider_accounts
        await show_openprovider_accounts(query, context)
    
    async def admin_dns_sync_handler(query, context):
        from handlers.core_handlers import handle_admin_dns_sync
        await handle_admin_dns_sync(query, context)
    
    async def cancel_broadcast_handler(query, context):
        from admin_handlers import handle_cancel_broadcast
        await handle_cancel_broadcast(query, context)
    
    async def admin_op_validate_handler(query, context):
        from handlers.core_handlers import handle_validate_openprovider_credentials
        await handle_validate_openprovider_credentials(query, context)
    
    async def admin_op_set_default_handler(query, context, account_id: str):
        from handlers.core_handlers import handle_set_default_openprovider_account
        await handle_set_default_openprovider_account(query, context, int(account_id))
    
    router.register_exact("admin_broadcast", admin_broadcast_handler)
    router.register_exact("admin_credit_wallet", admin_credit_handler)
    router.register_exact("admin_openprovider_accounts", admin_op_accounts_handler)
    router.register_exact("admin_openprovider", admin_op_accounts_handler)
    router.register_exact("admin_dns_sync", admin_dns_sync_handler)
    router.register_exact("cancel_broadcast", cancel_broadcast_handler)
    router.register_exact("admin_op_validate", admin_op_validate_handler)
    router.register_prefix("admin_op_set_default:", admin_op_set_default_handler)


# ============================================================================
# Router Factory
# ============================================================================

_router_instance: Optional[CallbackRouter] = None


def get_callback_router() -> CallbackRouter:
    """Get or create the callback router singleton"""
    global _router_instance
    
    if _router_instance is None:
        _router_instance = CallbackRouter()
        
        # Register all route groups
        create_core_routes(_router_instance)
        create_hosting_routes(_router_instance)
        create_rdp_routes(_router_instance)
        create_dns_routes(_router_instance)
        create_language_routes(_router_instance)
        create_admin_routes(_router_instance)
        
        logger.info(f"Callback router initialized with {len(_router_instance._exact_routes)} exact routes, "
                   f"{len(_router_instance._prefix_routes)} prefix routes, "
                   f"{len(_router_instance._startswith_routes)} startswith routes")
    
    return _router_instance


def reset_router() -> None:
    """Reset router for testing"""
    global _router_instance
    _router_instance = None
