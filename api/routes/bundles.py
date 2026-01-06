"""
Hosting Bundle Routes
"""
from decimal import Decimal
from fastapi import APIRouter, Depends, Query
from api.middleware.authentication import get_api_key_from_header, check_permission
from api.schemas.bundle import CreateDomainHostingBundleRequest
from api.utils.responses import success_response
from api.utils.errors import InternalServerError, BadRequestError
from services.hosting_orchestrator import HostingBundleOrchestrator
from services.openprovider import OpenProviderService
from database import (
    execute_query, 
    execute_update,
    reserve_wallet_balance,
    get_user_wallet_balance
)
import secrets

router = APIRouter()
hosting_orchestrator = HostingBundleOrchestrator()
openprovider = OpenProviderService()

import os

# Hosting pricing from environment secrets
def get_hosting_prices():
    """Get hosting prices from environment variables"""
    plan_7_price = Decimal(os.environ.get('HOSTING_PLAN_7_DAYS_PRICE', '40.00'))
    plan_30_price = Decimal(os.environ.get('HOSTING_PLAN_30_DAYS_PRICE', '80.00'))
    return {
        "pro_7day": plan_7_price,
        "pro_30day": plan_30_price
    }

HOSTING_PRICES = get_hosting_prices()


@router.post("/bundles/domain-hosting", response_model=dict)
async def create_domain_hosting_bundle(
    request: CreateDomainHostingBundleRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Register NEW domain + create hosting plan bundle - AUTOMATIC WALLET DEBIT.
    
    Creates both domain registration and hosting plan in one request.
    Wallet is immediately debited for domain + hosting cost.
    
    Use Case: Customer purchases a completely new domain with hosting together.
    """
    check_permission(key_data, "domains", "write")
    check_permission(key_data, "hosting", "write")
    user_id = key_data["user_id"]
    
    # Step 1: Get domain pricing (with 10% API discount)
    try:
        domain_pricing = await openprovider.get_domain_price(request.domain_name, request.period, is_api_purchase=True)
        if not domain_pricing or domain_pricing.get('create_price', 0) <= 0:
            raise InternalServerError("Failed to get domain pricing")
        
        domain_price = Decimal(str(domain_pricing.get('create_price')))
    except Exception as e:
        raise InternalServerError(f"Domain pricing error: {str(e)}")
    
    # Step 2: Calculate hosting price (with 10% API discount)
    hosting_price_per_period = HOSTING_PRICES.get(request.plan)
    if not hosting_price_per_period:
        raise BadRequestError(f"Invalid hosting plan: {request.plan}")
    
    # Apply 10% API discount to hosting
    hosting_price_before_discount = hosting_price_per_period * request.period
    api_discount = hosting_price_before_discount * Decimal("0.10")
    hosting_price = hosting_price_before_discount - api_discount
    
    # Step 3: Calculate total bundle price
    total_price = domain_price + hosting_price
    
    # Step 4: Check wallet balance
    current_balance = await get_user_wallet_balance(user_id)
    if current_balance < total_price:
        raise BadRequestError(
            f"Insufficient wallet balance. Required: ${total_price:.2f} (Domain: ${domain_price:.2f} + Hosting: ${hosting_price:.2f}), Available: ${current_balance:.2f}",
            {
                "required": float(total_price),
                "domain_price": float(domain_price),
                "hosting_price": float(hosting_price),
                "available": float(current_balance)
            }
        )
    
    # Step 5: Reserve wallet balance
    hold_transaction_id = await reserve_wallet_balance(
        user_id,
        total_price,
        f"Domain + Hosting Bundle: {request.domain_name}"
    )
    
    if not hold_transaction_id:
        raise InternalServerError("Failed to reserve wallet balance")
    
    # Step 6: Create hosting intent with hold_transaction_id
    intent_data = await execute_query("""
        INSERT INTO hosting_intents (
            user_id, domain_name, plan_name, service_type, status,
            created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
        RETURNING id
    """, (
        user_id, request.domain_name, request.plan, 
        'hosting_domain_bundle', 'pending'
    ))
    
    if not intent_data:
        raise InternalServerError("Failed to create hosting bundle intent")
    
    intent_row = intent_data[0]
    intent_id = intent_row['id'] if isinstance(intent_row, dict) else intent_row[0]
    
    # Step 7: Create order record with pricing breakdown
    order_data = await execute_query("""
        INSERT INTO orders (
            user_id, order_type, status, amount, description,
            external_order_id, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
    """, (
        user_id, 'domain_hosting_bundle', 'pending', float(total_price),
        f"Domain + Hosting Bundle: {request.domain_name} (Domain: ${domain_price}, Hosting: ${hosting_price})",
        f"bundle_{request.domain_name}_{user_id}_{secrets.token_hex(4)}"
    ))
    
    order_row = order_data[0]
    order_id = order_row['id'] if isinstance(order_row, dict) else order_row[0]
    
    # Step 8: Start orchestration with hold_transaction_id
    # Note: Orchestrator must call finalize_wallet_reservation(hold_transaction_id, success=True/False)
    import asyncio
    asyncio.create_task(hosting_orchestrator.start_hosting_bundle(
        order_id=order_id,
        user_id=user_id,
        domain_name=request.domain_name,
        payment_details={
            'plan': request.plan, 
            'period': request.period,
            'domain_price': float(domain_price),
            'hosting_price': float(hosting_price),
            'total_price': float(total_price),
            'hold_transaction_id': hold_transaction_id
        }
    ))
    
    return success_response({
        "bundle_id": intent_id,
        "order_id": order_id,
        "type": "domain_hosting",
        "domain_name": request.domain_name,
        "plan": request.plan,
        "status": "processing",
        "pricing": {
            "domain": {
                "base_price_usd": float(domain_pricing.get('base_price_usd', 0)),
                "tld_surcharge": float(domain_pricing.get('tld_surcharge', 0)),
                "price_before_discount": float(domain_pricing.get('price_before_discount', domain_price)),
                "api_discount": float(domain_pricing.get('api_discount', 0)),
                "final_price": float(domain_price)
            },
            "hosting": {
                "base_price_per_period": float(hosting_price_per_period),
                "periods": request.period,
                "price_before_discount": float(hosting_price_before_discount),
                "api_discount": float(api_discount),
                "final_price": float(hosting_price)
            },
            "total_price": float(total_price),
            "total_api_discount": float(domain_pricing.get('api_discount', 0) + api_discount)
        },
        "amount_reserved": float(total_price),
        "hold_transaction_id": hold_transaction_id
    }, "Domain + hosting bundle creation started - wallet funds reserved")


@router.get("/bundles/{bundle_id}", response_model=dict)
async def get_bundle(
    bundle_id: int,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get bundle details"""
    check_permission(key_data, "hosting", "read")
    user_id = key_data["user_id"]
    
    from api.utils.errors import ResourceNotFoundError
    
    result = await execute_query("""
        SELECT id, domain_name, plan_name, service_type, status, 
               created_at, updated_at
        FROM hosting_intents
        WHERE id = %s AND user_id = %s AND service_type = 'hosting_domain_bundle'
    """, (bundle_id, user_id))
    
    if not result:
        raise ResourceNotFoundError("Bundle", str(bundle_id))
    
    bundle = result[0]
    
    return success_response({
        "id": bundle[0],
        "type": "domain_hosting",
        "domain_name": bundle[1],
        "plan": bundle[2],
        "status": bundle[4],
        "created_at": bundle[5].isoformat() + "Z" if bundle[5] else None,
        "updated_at": bundle[6].isoformat() + "Z" if bundle[6] else None
    })


@router.get("/bundles", response_model=dict)
async def list_bundles(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    key_data: dict = Depends(get_api_key_from_header)
):
    """List all bundles"""
    check_permission(key_data, "hosting", "read")
    user_id = key_data["user_id"]
    
    offset = (page - 1) * per_page
    
    result = await execute_query("""
        SELECT id, domain_name, plan_name, service_type, status, created_at
        FROM hosting_intents
        WHERE user_id = %s AND service_type = 'hosting_domain_bundle'
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """, (user_id, per_page, offset))
    
    bundles = [{
        "id": b[0],
        "type": "domain_hosting",
        "domain_name": b[1],
        "plan": b[2],
        "status": b[4],
        "created_at": b[5].isoformat() + "Z" if b[5] else None
    } for b in result]
    
    return success_response({
        "bundles": bundles,
        "total": len(bundles),
        "page": page,
        "per_page": per_page
    })
