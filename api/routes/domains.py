"""
Domain Registration & Management Routes
"""
from decimal import Decimal
import json
from fastapi import APIRouter, Depends, Query
from api.middleware.authentication import get_api_key_from_header, check_permission
from api.schemas.domain import (
    RegisterDomainRequest,
    BulkRegisterRequest,
    TransferDomainRequest,
    RenewDomainRequest,
    UpdateContactsRequest,
    DomainResponse
)
from api.utils.responses import success_response
from api.utils.errors import ResourceNotFoundError, InternalServerError, BadRequestError
from services.openprovider import OpenProviderService
from api.services.domain_coordinator import DomainRegistrationCoordinator
from api.constants import get_privacy_guard_handle
from database import (
    execute_query,
    execute_update, 
    reserve_wallet_balance, 
    finalize_wallet_reservation,
    get_user_wallet_balance_by_id
)
from admin_alerts import send_info_alert, send_error_alert
from webhook_handler import queue_user_message
from localization import t_for_user
import logging
import time

logger = logging.getLogger(__name__)

router = APIRouter()
openprovider = OpenProviderService()
domain_coordinator = DomainRegistrationCoordinator()


@router.post("/domains/register", response_model=dict)
async def register_domain(
    request: RegisterDomainRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Register a new domain with automatic wallet debit on success or refund on failure.
    
    Financial Flow:
    1. Check wallet balance
    2. Get domain pricing from OpenProvider
    3. Reserve wallet funds (hold)
    4. Attempt domain registration
    5. On success: Debit wallet (finalize hold)
    6. On failure: Refund wallet (cancel hold)
    """
    check_permission(key_data, "domains", "write")
    user_id = key_data["user_id"]
    
    # PERFORMANCE OPTIMIZATION: Fetch wallet balance and pricing in parallel
    import asyncio
    try:
        balance_task = get_user_wallet_balance_by_id(user_id)
        pricing_task = openprovider.get_domain_price(request.domain_name, request.period, is_api_purchase=True)
        current_balance, pricing_result = await asyncio.gather(balance_task, pricing_task)
        
        if not pricing_result or pricing_result.get('create_price', 0) <= 0:
            raise InternalServerError("Failed to get domain pricing")
        
        total_price = Decimal(str(pricing_result.get('create_price')))
        
    except Exception as e:
        raise InternalServerError(f"Pricing error: {str(e)}")
    
    # Step 3: Check sufficient balance
    if current_balance < total_price:
        raise BadRequestError(
            f"Insufficient wallet balance. Required: ${total_price:.2f}, Available: ${current_balance:.2f}",
            {"required": float(total_price), "available": float(current_balance)}
        )
    
    # Step 4: Reserve wallet balance (hold funds)
    hold_transaction_id = await reserve_wallet_balance(
        user_id,
        total_price,
        f"Domain registration hold: {request.domain_name}"
    )
    
    if not hold_transaction_id:
        raise InternalServerError("Failed to reserve wallet balance")
    
    # Step 5: Attempt domain registration via coordinator
    registration_success = False
    registration_result = None
    
    try:
        registration_result = await domain_coordinator.register_domain(request, user_id)
        registration_success = bool(registration_result and registration_result.get('success', False))
        
    except Exception as e:
        registration_success = False
        registration_result = {'success': False, 'error': str(e)}
    
    # Step 6: Finalize wallet payment based on registration outcome
    finalization_success = await finalize_wallet_reservation(
        hold_transaction_id, 
        success=bool(registration_success)
    )
    
    if not finalization_success:
        raise InternalServerError(
            "Financial settlement failed - please contact support",
            {"hold_id": hold_transaction_id, "registration_success": registration_success}
        )
    
    # Step 7: Return result with pricing breakdown
    if registration_success:
        # Send admin success notification
        await send_info_alert(
            "DomainAPI",
            f"✅ Domain registered via API: {request.domain_name} for user {user_id}",
            "domain_registration",
            {
                "domain_name": request.domain_name,
                "user_id": user_id,
                "payment_method": "API (wallet)",
                "amount": float(total_price)
            }
        )
        
        # Send user Telegram notification
        try:
            user_message = (
                f"✅ {t_for_user(user_id, 'domain_registered_title')}\n\n"
                f"🌐 {t_for_user(user_id, 'domain')}: {request.domain_name}\n"
                f"💰 {t_for_user(user_id, 'amount')}: ${float(total_price):.2f}\n"
                f"📅 {t_for_user(user_id, 'period')}: {request.period} {t_for_user(user_id, 'year' if request.period == 1 else 'years')}\n"
                f"🔄 {t_for_user(user_id, 'auto_renew')}: {'✓' if request.auto_renew else '✗'}\n\n"
                f"💼 {t_for_user(user_id, 'order_via_api')}"
            )
            await queue_user_message(user_id, user_message)
            logger.info(f"📱 Sent domain registration notification to user {user_id}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to send user notification for domain registration: {e}")
        
        return success_response({
            "domain_name": request.domain_name,
            "status": "active",
            "openprovider_id": registration_result.get('domain_id') if registration_result else None,
            "auto_renew": request.auto_renew,
            "pricing": {
                "base_price_usd": float(pricing_result.get('base_price_usd', 0)),
                "markup_applied": float(pricing_result.get('markup_applied', 0)),
                "tld_surcharge": float(pricing_result.get('tld_surcharge', 0)),
                "price_before_discount": float(pricing_result.get('price_before_discount', total_price)),
                "api_discount": float(pricing_result.get('api_discount', 0)),
                "final_price": float(total_price)
            },
            "amount_charged": float(total_price),
            "wallet_balance_remaining": float(current_balance - total_price)
        }, "Domain registered successfully with 10% API discount")
    else:
        error_message = registration_result.get('error', 'Unknown error') if registration_result else 'Unknown error'
        
        # Send admin failure notification
        await send_error_alert(
            "DomainAPI",
            f"❌ Domain registration failed via API: {request.domain_name} for user {user_id}",
            "domain_registration",
            {
                "domain_name": request.domain_name,
                "user_id": user_id,
                "error": error_message
            }
        )
        
        raise InternalServerError(
            f"Domain registration failed: {error_message}. Wallet balance refunded.",
            {"error": error_message, "refunded": True}
        )


@router.post("/domains/bulk-register", response_model=dict)
async def bulk_register_domains(
    request: BulkRegisterRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Register multiple domains with automatic wallet debit per domain.
    
    NOTE: Each domain is processed independently with its own wallet reservation.
    If one domain fails, others can still succeed. Failed domains are refunded.
    """
    check_permission(key_data, "domains", "write")
    user_id = key_data["user_id"]
    
    # Get current wallet balance once
    current_balance = await get_user_wallet_balance_by_id(user_id)
    
    results = []
    total_reserved = Decimal("0")
    
    for domain_req in request.domains:
        try:
            # Step 1: Get pricing for this domain (with 10% API discount)
            pricing_result = await openprovider.get_domain_price(domain_req.domain_name, domain_req.period, is_api_purchase=True)
            if not pricing_result or pricing_result.get('create_price', 0) <= 0:
                results.append({
                    "domain_name": domain_req.domain_name,
                    "success": False,
                    "error": "Failed to get domain pricing"
                })
                continue
            
            domain_price = Decimal(str(pricing_result.get('create_price')))
            
            # Step 2: Check if sufficient balance remains
            if current_balance < (total_reserved + domain_price):
                results.append({
                    "domain_name": domain_req.domain_name,
                    "success": False,
                    "error": f"Insufficient balance for domain {domain_req.domain_name}. Required: ${domain_price:.2f}, Remaining: ${(current_balance - total_reserved):.2f}"
                })
                continue
            
            # Step 3: Reserve wallet balance for this domain
            hold_id = await reserve_wallet_balance(
                user_id,
                domain_price,
                f"Bulk registration hold: {domain_req.domain_name}"
            )
            
            if not hold_id:
                results.append({
                    "domain_name": domain_req.domain_name,
                    "success": False,
                    "error": "Failed to reserve wallet balance"
                })
                continue
            
            total_reserved += domain_price
            
            # Step 4: Attempt registration via coordinator
            registration_success = False
            registration_result = None
            
            try:
                registration_result = await domain_coordinator.register_domain(domain_req, user_id)
                registration_success = bool(registration_result and registration_result.get('success', False))
            except Exception as reg_error:
                registration_success = False
                registration_result = {'success': False, 'error': str(reg_error)}
            
            # Step 5: Finalize wallet payment
            finalization_success = await finalize_wallet_reservation(hold_id, success=bool(registration_success))
            
            # Step 6: Record result
            if registration_success and finalization_success:
                results.append({
                    "domain_name": domain_req.domain_name,
                    "success": True,
                    "openprovider_id": registration_result.get('domain_id') if registration_result else None,
                    "amount_charged": float(domain_price)
                })
            elif registration_success and not finalization_success:
                results.append({
                    "domain_name": domain_req.domain_name,
                    "success": False,
                    "error": "Domain registered but payment settlement failed - contact support"
                })
            else:
                results.append({
                    "domain_name": domain_req.domain_name,
                    "success": False,
                    "error": registration_result.get('error', 'Unknown error') if registration_result else 'Unknown error',
                    "refunded": finalization_success
                })
                
        except Exception as e:
            results.append({
                "domain_name": domain_req.domain_name,
                "success": False,
                "error": f"Exception: {str(e)}"
            })
    
    successful_count = sum(1 for r in results if r.get('success'))
    failed_count = len(results) - successful_count
    
    return success_response({
        "results": results,
        "total": len(results),
        "successful": successful_count,
        "failed": failed_count,
        "total_charged": float(total_reserved)
    })


@router.post("/domains/transfer", response_model=dict)
async def transfer_domain(
    request: TransferDomainRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Transfer a domain from another registrar with automatic wallet debit.
    
    Financial Flow:
    1. Get transfer pricing from OpenProvider
    2. Check wallet balance
    3. Reserve wallet funds (hold)
    4. Attempt domain transfer
    5. On success: Debit wallet (finalize hold)
    6. On failure: Refund wallet (cancel hold)
    """
    check_permission(key_data, "domains", "write")
    user_id = key_data["user_id"]
    
    try:
        pricing_result = await openprovider.get_domain_price(request.domain_name, 1, is_api_purchase=True)
        if not pricing_result or pricing_result.get('create_price', 0) <= 0:
            raise InternalServerError("Failed to get transfer pricing")
        
        total_price = Decimal(str(pricing_result.get('create_price')))
        
    except Exception as e:
        raise InternalServerError(f"Pricing error: {str(e)}")
    
    current_balance = await get_user_wallet_balance_by_id(user_id)
    if current_balance < total_price:
        raise BadRequestError(
            f"Insufficient balance. Required: ${total_price:.2f}, Available: ${current_balance:.2f}",
            {"required": float(total_price), "available": float(current_balance)}
        )
    
    hold_transaction_id = await reserve_wallet_balance(
        user_id, total_price, f"Domain transfer: {request.domain_name}"
    )
    
    if not hold_transaction_id:
        raise InternalServerError("Failed to reserve wallet balance")
    
    try:
        transfer_result = await openprovider.transfer_domain(
            request.domain_name, request.auth_code, 1
        )
        success = bool(transfer_result and transfer_result.get('success'))
    except Exception as e:
        success = False
        transfer_result = {'error': str(e)}
    
    await finalize_wallet_reservation(hold_transaction_id, success=bool(success))
    
    if success:
        return success_response({
            "domain_name": request.domain_name,
            "status": "transfer_pending",
            "domain_id": transfer_result.get('domain_id') if transfer_result else None,
            "pricing": {
                "base_price_usd": float(pricing_result.get('base_price_usd', 0)),
                "markup_applied": float(pricing_result.get('markup_applied', 0)),
                "tld_surcharge": float(pricing_result.get('tld_surcharge', 0)),
                "price_before_discount": float(pricing_result.get('price_before_discount', total_price)),
                "api_discount": float(pricing_result.get('api_discount', 0)),
                "final_price": float(total_price)
            },
            "amount_charged": float(total_price)
        }, "Domain transfer initiated successfully with 10% API discount")
    else:
        error_msg = transfer_result.get('error', 'Unknown error') if transfer_result else 'Unknown error'
        raise InternalServerError(
            f"Domain transfer failed: {error_msg}. Wallet refunded.",
            {"error": error_msg, "refunded": True}
        )


@router.get("/domains", response_model=dict)
async def list_domains(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    key_data: dict = Depends(get_api_key_from_header)
):
    """List all domains"""
    check_permission(key_data, "domains", "read")
    user_id = key_data["user_id"]
    
    offset = (page - 1) * per_page
    
    domains = await execute_query("""
        SELECT domain_name, status, created_at, provider_domain_id, cloudflare_zone_id
        FROM domains
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """, (user_id, per_page, offset))
    
    total_result = await execute_query("""
        SELECT COUNT(*) as count FROM domains WHERE user_id = %s
    """, (user_id,))
    total = total_result[0]['count'] if total_result else 0
    
    domain_list = [{
        "domain_name": d['domain_name'],
        "status": d['status'],
        "created_at": d['created_at'].isoformat() if d.get('created_at') else None,
        # New generic field names
        "registry_id": d.get('provider_domain_id'),
        "dns_zone_id": d.get('cloudflare_zone_id'),
        # Legacy field names (backward compatibility)
        "provider_id": d.get('provider_domain_id'),
        "cloudflare_zone_id": d.get('cloudflare_zone_id')
    } for d in domains]
    
    return success_response({
        "domains": domain_list,
        "total": total,
        "page": page,
        "per_page": per_page
    })


@router.get("/domains/{domain_name}", response_model=dict)
async def get_domain(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get domain information"""
    check_permission(key_data, "domains", "read")
    user_id = key_data["user_id"]
    
    result = await execute_query("""
        SELECT domain_name, status, created_at, updated_at, provider_domain_id, cloudflare_zone_id,
               contact_type, privacy_enabled
        FROM domains
        WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    d = result[0]
    return success_response({
        "domain_name": d['domain_name'],
        "status": d['status'],
        "created_at": d['created_at'].isoformat() if d.get('created_at') else None,
        "updated_at": d['updated_at'].isoformat() if d.get('updated_at') else None,
        # New generic field names
        "registry_id": d.get('provider_domain_id'),
        "dns_zone_id": d.get('cloudflare_zone_id'),
        # Legacy field names (backward compatibility)
        "provider_id": d.get('provider_domain_id'),
        "cloudflare_zone_id": d.get('cloudflare_zone_id'),
        "contact_type": d.get('contact_type', 'hostbay_managed'),
        "privacy_enabled": d.get('privacy_enabled', False),
        "auto_renew": True,
        "is_locked": False
    })


@router.post("/domains/{domain_name}/renew", response_model=dict)
async def renew_domain(
    domain_name: str,
    request: RenewDomainRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Renew a domain with automatic wallet debit.
    
    Financial Flow:
    1. Get domain from database
    2. Get renewal pricing
    3. Check wallet balance
    4. Reserve wallet funds (hold)
    5. Attempt domain renewal
    6. On success: Debit wallet (finalize hold)
    7. On failure: Refund wallet (cancel hold)
    """
    check_permission(key_data, "domains", "write")
    user_id = key_data["user_id"]
    
    from database import execute_update
    
    domain_result = await execute_query("""
        SELECT provider_domain_id, expires_at 
        FROM domains 
        WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    openprovider_id = domain_result[0]['provider_domain_id']
    
    try:
        pricing_result = await openprovider.get_domain_price(domain_name, request.period, is_api_purchase=True)
        if not pricing_result or pricing_result.get('create_price', 0) <= 0:
            raise InternalServerError("Failed to get renewal pricing")
        
        total_price = Decimal(str(pricing_result.get('create_price')))
        
    except Exception as e:
        raise InternalServerError(f"Pricing error: {str(e)}")
    
    current_balance = await get_user_wallet_balance_by_id(user_id)
    if current_balance < total_price:
        raise BadRequestError(
            f"Insufficient balance. Required: ${total_price:.2f}, Available: ${current_balance:.2f}",
            {"required": float(total_price), "available": float(current_balance)}
        )
    
    hold_transaction_id = await reserve_wallet_balance(
        user_id, total_price, f"Domain renewal: {domain_name}"
    )
    
    if not hold_transaction_id:
        raise InternalServerError("Failed to reserve wallet balance")
    
    try:
        renewal_result = await openprovider.renew_domain(openprovider_id, request.period)
        success = bool(renewal_result and renewal_result.get('success'))
    except Exception as e:
        success = False
        renewal_result = {'error': str(e)}
    
    await finalize_wallet_reservation(hold_transaction_id, success=bool(success))
    
    if success:
        new_expires_at = renewal_result.get('new_expires_at') if renewal_result else None
        if new_expires_at:
            await execute_update("""
                UPDATE domains 
                SET expires_at = %s, updated_at = CURRENT_TIMESTAMP
                WHERE domain_name = %s
            """, (new_expires_at, domain_name))
        
        return success_response({
            "domain_name": domain_name,
            "renewed": True,
            "period": request.period,
            "new_expires_at": new_expires_at,
            "pricing": {
                "base_price_usd": float(pricing_result.get('base_price_usd', 0)),
                "markup_applied": float(pricing_result.get('markup_applied', 0)),
                "tld_surcharge": float(pricing_result.get('tld_surcharge', 0)),
                "price_before_discount": float(pricing_result.get('price_before_discount', total_price)),
                "api_discount": float(pricing_result.get('api_discount', 0)),
                "final_price": float(total_price)
            },
            "amount_charged": float(total_price)
        }, "Domain renewed successfully with 10% API discount")
    else:
        error_msg = renewal_result.get('error', 'Unknown error') if renewal_result else 'Unknown error'
        raise InternalServerError(
            f"Domain renewal failed: {error_msg}. Wallet refunded.",
            {"error": error_msg, "refunded": True}
        )


@router.delete("/domains/{domain_name}", response_model=dict)
async def delete_domain(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Cancel/delete a domain via OpenProvider"""
    check_permission(key_data, "domains", "write")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT provider_domain_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    openprovider_id = domain_result[0]['provider_domain_id']
    
    delete_result = await openprovider.delete_domain(openprovider_id)
    
    if delete_result and delete_result.get('success'):
        return success_response({
            "domain_name": domain_name,
            "deleted": True
        }, "Domain cancellation requested")
    else:
        error_msg = delete_result.get('error', 'Unknown error') if delete_result else 'Unknown error'
        raise InternalServerError(f"Domain deletion failed: {error_msg}")


@router.get("/domains/{domain_name}/whois", response_model=dict)
async def get_whois(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get WHOIS information for a domain"""
    check_permission(key_data, "domains", "read")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    whois_result = await openprovider.get_whois_info(domain_name)
    
    if whois_result and whois_result.get('success'):
        return success_response({
            "domain": domain_name,
            "whois_data": whois_result.get('whois_data', {})
        })
    else:
        raise InternalServerError("Failed to retrieve WHOIS information")


@router.get("/domains/{domain_name}/auth-code", response_model=dict)
async def get_auth_code(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get EPP/Auth code for domain transfer"""
    check_permission(key_data, "domains", "read")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT provider_domain_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    openprovider_id = domain_result[0]['provider_domain_id']
    
    auth_result = await openprovider.get_auth_code(openprovider_id)
    
    if auth_result and auth_result.get('success'):
        return success_response({
            "domain": domain_name,
            "auth_code": auth_result.get('auth_code')
        })
    else:
        raise InternalServerError("Failed to retrieve auth code")


@router.post("/domains/{domain_name}/lock", response_model=dict)
async def lock_domain(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Lock domain to prevent unauthorized transfers"""
    check_permission(key_data, "domains", "write")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT provider_domain_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    openprovider_id = domain_result[0]['provider_domain_id']
    
    lock_result = await openprovider.lock_domain(openprovider_id)
    
    if lock_result and lock_result.get('success'):
        return success_response({
            "domain": domain_name,
            "locked": True
        }, "Domain locked successfully")
    else:
        error_msg = lock_result.get('error', 'Unknown error') if lock_result else 'Unknown error'
        raise InternalServerError(f"Failed to lock domain: {error_msg}")


@router.post("/domains/{domain_name}/unlock", response_model=dict)
async def unlock_domain(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Unlock domain to allow transfers"""
    check_permission(key_data, "domains", "write")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT provider_domain_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    openprovider_id = domain_result[0]['provider_domain_id']
    
    unlock_result = await openprovider.unlock_domain(openprovider_id)
    
    if unlock_result and unlock_result.get('success'):
        return success_response({
            "domain": domain_name,
            "locked": False
        }, "Domain unlocked successfully")
    else:
        error_msg = unlock_result.get('error', 'Unknown error') if unlock_result else 'Unknown error'
        raise InternalServerError(f"Failed to unlock domain: {error_msg}")


@router.post("/domains/{domain_name}/auth-code/reset", response_model=dict)
async def reset_auth_code(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Reset/regenerate EPP authorization code for domain transfer.
    Useful when auth code is lost or compromised.
    """
    check_permission(key_data, "domains", "write")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT provider_domain_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    openprovider_id = domain_result[0]['provider_domain_id']
    
    reset_result = await openprovider.reset_auth_code(openprovider_id)
    
    if reset_result and reset_result.get('success'):
        return success_response({
            "domain": domain_name,
            "auth_code": reset_result.get('auth_code'),
            "type": reset_result.get('type', 'internal')
        }, "Auth code reset successfully")
    else:
        error_msg = reset_result.get('error', 'Unknown error') if reset_result else 'Unknown error'
        raise InternalServerError(f"Failed to reset auth code: {error_msg}")


@router.post("/domains/{domain_name}/transfer/approve", response_model=dict)
async def approve_outgoing_transfer(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header),
    registrar_tag: str = Query('', description="Registrar tag (optional, required for some TLDs)")
):
    """
    Approve outgoing domain transfer.
    Speeds up transfer process instead of waiting 5 days for auto-approval.
    """
    check_permission(key_data, "domains", "write")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT provider_domain_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    openprovider_id = domain_result[0]['provider_domain_id']
    
    approve_result = await openprovider.approve_transfer(openprovider_id, domain_name, registrar_tag)
    
    if approve_result and approve_result.get('success'):
        return success_response({
            "domain": domain_name,
            "approved": True,
            "message": "Transfer approved successfully"
        }, "Outgoing transfer approved")
    else:
        error_msg = approve_result.get('error', 'Unknown error') if approve_result else 'Unknown error'
        raise InternalServerError(f"Failed to approve transfer: {error_msg}")


@router.post("/domains/{domain_name}/transfer/reject", response_model=dict)
async def reject_outgoing_transfer(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Reject outgoing domain transfer.
    Blocks unauthorized transfer attempts.
    """
    check_permission(key_data, "domains", "write")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT provider_domain_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    openprovider_id = domain_result[0]['provider_domain_id']
    
    reject_result = await openprovider.reject_transfer(openprovider_id, domain_name)
    
    if reject_result and reject_result.get('success'):
        return success_response({
            "domain": domain_name,
            "rejected": True,
            "message": "Transfer rejected successfully"
        }, "Outgoing transfer rejected")
    else:
        error_msg = reject_result.get('error', 'Unknown error') if reject_result else 'Unknown error'
        raise InternalServerError(f"Failed to reject transfer: {error_msg}")


@router.post("/domains/{domain_name}/transfer/restart", response_model=dict)
async def restart_failed_transfer(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Restart a failed domain transfer operation.
    Useful for retrying stuck or failed transfers.
    """
    check_permission(key_data, "domains", "write")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT provider_domain_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    openprovider_id = domain_result[0]['provider_domain_id']
    
    restart_result = await openprovider.restart_transfer(openprovider_id, domain_name)
    
    if restart_result and restart_result.get('success'):
        return success_response({
            "domain": domain_name,
            "restarted": True,
            "message": "Transfer restarted successfully"
        }, "Transfer operation restarted")
    else:
        error_msg = restart_result.get('error', 'Unknown error') if restart_result else 'Unknown error'
        raise InternalServerError(f"Failed to restart transfer: {error_msg}")


@router.get("/domains/transfer/eligibility/{domain_name}", response_model=dict)
async def check_transfer_eligibility(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Check if a domain is eligible for transfer to HostBay.
    
    This endpoint verifies:
    1. Domain is registered (not available for new registration)
    2. Domain is at least 60 days old (ICANN transfer policy)
    3. Domain is not locked (no clientTransferProhibited status)
    
    Returns eligibility status, reasons, and transfer pricing if eligible.
    """
    check_permission(key_data, "domains", "read")
    
    eligibility_result = await openprovider.check_transfer_eligibility(domain_name)
    
    return success_response({
        "domain_name": eligibility_result.get('domain_name'),
        "eligible": eligibility_result.get('eligible', False),
        "reasons": eligibility_result.get('reasons', []),
        "checks": eligibility_result.get('checks', {}),
        "transfer_price_usd": eligibility_result.get('transfer_price_usd')
    }, "Transfer eligibility check completed")


@router.post("/domains/transfer", response_model=dict)
async def initiate_domain_transfer(
    request: TransferDomainRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Initiate domain transfer from another registrar to HostBay.
    Requires EPP/auth code from current registrar.
    """
    check_permission(key_data, "domains", "write")
    user_id = key_data["user_id"]
    
    transfer_result = await openprovider.transfer_domain(
        request.domain_name,
        request.auth_code,
        request.period
    )
    
    if transfer_result and transfer_result.get('success'):
        return success_response({
            "domain": request.domain_name,
            "status": "transfer_pending",
            "openprovider_id": transfer_result.get('domain_id'),
            "period": request.period,
            "message": "Transfer initiated - typically completes in 5-7 days"
        }, "Domain transfer initiated successfully")
    else:
        error_msg = transfer_result.get('error', 'Unknown error') if transfer_result else 'Unknown error'
        raise InternalServerError(f"Failed to initiate transfer: {error_msg}")


@router.post("/domains/{domain_name}/privacy/enable", response_model=dict)
async def enable_privacy(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Enable WHOIS privacy protection for domain.
    
    Logic:
    - For user-provided contacts: Replace with Privacy Guard contact and store original
    - For HostBay-managed contacts: Do nothing (already private)
    """
    check_permission(key_data, "domains", "write")
    user_id = key_data["user_id"]
    
    # Get domain with contact type
    domain_result = await execute_query("""
        SELECT provider_domain_id, contact_type, privacy_enabled, original_contact_data
        FROM domains 
        WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    domain = domain_result[0]
    openprovider_id = domain['provider_domain_id']
    contact_type = domain.get('contact_type', 'hostbay_managed')
    already_enabled = domain.get('privacy_enabled', False)
    
    # If already enabled, return success
    if already_enabled:
        return success_response({
            "domain": domain_name,
            "privacy_enabled": True,
            "message": "Privacy protection already enabled"
        }, "Privacy protection is already active")
    
    # If HostBay-managed contact, do nothing (already private)
    if contact_type == 'hostbay_managed':
        await execute_update("""
            UPDATE domains 
            SET privacy_enabled = TRUE, updated_at = CURRENT_TIMESTAMP
            WHERE domain_name = %s
        """, (domain_name,))
        
        return success_response({
            "domain": domain_name,
            "privacy_enabled": True,
            "contact_type": "hostbay_managed",
            "message": "Using HostBay-managed contact (already private)"
        }, "Privacy protection enabled (shared contact)")
    
    # For user-provided contacts: get current contact, store it, and replace with Privacy Guard
    if not openprovider_id:
        raise BadRequestError("Domain registration data not found - cannot enable privacy")
    
    # Get current domain contact info from OpenProvider
    whois_info = await openprovider.get_whois_info(domain_name)
    if not whois_info or not whois_info.get('success'):
        raise InternalServerError("Failed to retrieve current contact information")
    
    # Store original contact data for reverting later
    original_contact = whois_info.get('whois_data', {})
    
    # Get Privacy Guard contact handle
    privacy_guard_contact = get_privacy_guard_handle()
    
    # Update domain contacts to Privacy Guard
    contacts_payload = {
        "owner": privacy_guard_contact,
        "admin": privacy_guard_contact,
        "tech": privacy_guard_contact,
        "billing": privacy_guard_contact
    }
    
    update_result = await openprovider.update_domain_contacts(openprovider_id, contacts_payload)
    
    if not update_result or not update_result.get('success'):
        error_msg = update_result.get('error', 'Unknown error') if update_result else 'Unknown error'
        raise InternalServerError(f"Failed to update contacts: {error_msg}")
    
    # Update database with privacy status and original contact
    await execute_update("""
        UPDATE domains 
        SET privacy_enabled = TRUE,
            original_contact_data = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE domain_name = %s
    """, (json.dumps(original_contact), domain_name))
    
    return success_response({
        "domain": domain_name,
        "privacy_enabled": True,
        "contact_type": "user_provided",
        "privacy_guard_applied": True
    }, "WHOIS privacy enabled - contacts replaced with Privacy Guard")


@router.post("/domains/{domain_name}/privacy/disable", response_model=dict)
async def disable_privacy(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Disable WHOIS privacy protection for domain.
    
    Logic:
    - For user-provided contacts: Restore original user contact from stored data
    - For HostBay-managed contacts: Do nothing (keep shared contact)
    """
    check_permission(key_data, "domains", "write")
    user_id = key_data["user_id"]
    
    # Get domain with contact type and original contact data
    domain_result = await execute_query("""
        SELECT provider_domain_id, contact_type, privacy_enabled, original_contact_data
        FROM domains 
        WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    domain = domain_result[0]
    openprovider_id = domain['provider_domain_id']
    contact_type = domain.get('contact_type', 'hostbay_managed')
    privacy_enabled = domain.get('privacy_enabled', False)
    original_contact_data = domain.get('original_contact_data')
    
    # If already disabled, return success
    if not privacy_enabled:
        return success_response({
            "domain": domain_name,
            "privacy_enabled": False,
            "message": "Privacy protection already disabled"
        }, "Privacy protection is already inactive")
    
    # If HostBay-managed contact, just update status
    if contact_type == 'hostbay_managed':
        await execute_update("""
            UPDATE domains 
            SET privacy_enabled = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE domain_name = %s
        """, (domain_name,))
        
        return success_response({
            "domain": domain_name,
            "privacy_enabled": False,
            "contact_type": "hostbay_managed",
            "message": "HostBay-managed contact unchanged"
        }, "Privacy protection disabled (shared contact unchanged)")
    
    # For user-provided contacts: restore original contact
    if not openprovider_id:
        raise BadRequestError("Domain registration data not found - cannot disable privacy")
    
    if not original_contact_data:
        raise BadRequestError("No original contact data stored - cannot restore contacts")
    
    # Parse original contact data
    try:
        original_contact = json.loads(original_contact_data) if isinstance(original_contact_data, str) else original_contact_data
    except json.JSONDecodeError:
        raise InternalServerError("Failed to parse original contact data")
    
    # Restore original contacts
    # Note: OpenProvider expects specific contact format - we'll use the contacts from WHOIS data
    contacts_payload = {
        "owner": original_contact.get('owner', {}),
        "admin": original_contact.get('admin', {}),
        "tech": original_contact.get('tech', {}),
        "billing": original_contact.get('billing', {})
    }
    
    update_result = await openprovider.update_domain_contacts(openprovider_id, contacts_payload)
    
    if not update_result or not update_result.get('success'):
        error_msg = update_result.get('error', 'Unknown error') if update_result else 'Unknown error'
        raise InternalServerError(f"Failed to restore contacts: {error_msg}")
    
    # Update database - clear privacy and original contact data
    await execute_update("""
        UPDATE domains 
        SET privacy_enabled = FALSE,
            original_contact_data = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE domain_name = %s
    """, (domain_name,))
    
    return success_response({
        "domain": domain_name,
        "privacy_enabled": False,
        "contact_type": "user_provided",
        "original_contacts_restored": True
    }, "WHOIS privacy disabled - original contacts restored")


@router.put("/domains/{domain_name}/contacts", response_model=dict)
async def update_contacts(
    domain_name: str,
    request: UpdateContactsRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Update domain contact information"""
    check_permission(key_data, "domains", "write")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT provider_domain_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    openprovider_id = domain_result[0]['provider_domain_id']
    
    # Build contacts dictionary from request fields
    contacts = {}
    if request.registrant:
        contacts['registrant'] = request.registrant.dict()
    if request.admin:
        contacts['admin'] = request.admin.dict()
    if request.tech:
        contacts['tech'] = request.tech.dict()
    if request.billing:
        contacts['billing'] = request.billing.dict()
    
    contacts_result = await openprovider.update_domain_contacts(
        openprovider_id, contacts
    )
    
    if contacts_result and contacts_result.get('success'):
        return success_response({
            "domain": domain_name,
            "contacts_updated": True
        }, "Domain contacts updated successfully")
    else:
        error_msg = contacts_result.get('error', 'Unknown error') if contacts_result else 'Unknown error'
        raise InternalServerError(f"Failed to update contacts: {error_msg}")
