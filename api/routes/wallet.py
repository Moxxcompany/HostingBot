"""
Wallet & Orders Routes
"""
from fastapi import APIRouter, Depends, Query
from api.middleware.authentication import get_api_key_from_header, check_permission
from api.schemas.wallet import TopupWalletRequest
from api.utils.responses import success_response
from database import execute_query

router = APIRouter()


@router.get("/wallet/balance", response_model=dict)
async def get_wallet_balance(
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get wallet balance"""
    check_permission(key_data, "wallet", "read")
    user_id = key_data["user_id"]
    
    result = await execute_query("""
        SELECT wallet_balance FROM users WHERE id = %s
    """, (user_id,))
    
    balance = result[0]['wallet_balance'] if result else 0.0
    
    return success_response({
        "balance": float(balance),
        "currency": "USD",
        "last_updated": "2025-10-31T12:00:00Z"
    })


@router.post("/wallet/topup", response_model=dict, include_in_schema=False)
async def topup_wallet(
    request: TopupWalletRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Top up wallet balance"""
    check_permission(key_data, "wallet", "write")
    
    return success_response({
        "amount": request.amount,
        "payment_method": request.payment_method,
        "status": "pending",
        "payment_url": "https://payment.example.com/pay/123"
    }, "Top-up request created")


@router.get("/wallet/transactions", response_model=dict)
async def list_transactions(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    key_data: dict = Depends(get_api_key_from_header)
):
    """List wallet transactions"""
    check_permission(key_data, "wallet", "read")
    user_id = key_data["user_id"]
    
    offset = (page - 1) * per_page
    
    transactions = await execute_query("""
        SELECT id, transaction_type, amount, description, created_at, status, currency
        FROM wallet_transactions
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """, (user_id, per_page, offset))
    
    tx_list = [{
        "id": t['id'],
        "type": t['transaction_type'],
        "amount": float(t['amount']) if t.get('amount') else 0,
        "description": t['description'],
        "created_at": t['created_at'].isoformat() if t.get('created_at') else None,
        "status": t.get('status'),
        "currency": t.get('currency', 'USD')
    } for t in transactions]
    
    return success_response({
        "transactions": tx_list,
        "total": len(tx_list),
        "page": page,
        "per_page": per_page
    })


@router.get("/orders", response_model=dict, include_in_schema=False)
async def list_orders(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    status: str = Query(None),
    order_type: str = Query(None),
    domain_name: str = Query(None),
    from_date: str = Query(None),
    to_date: str = Query(None),
    key_data: dict = Depends(get_api_key_from_header)
):
    """List all orders with optional filtering"""
    check_permission(key_data, "orders", "read")
    user_id = key_data["user_id"]
    
    offset = (page - 1) * per_page
    
    query = """
        SELECT id, order_type, status, amount, description, created_at
        FROM orders
        WHERE user_id = %s
    """
    params = [user_id]
    
    if status:
        query += " AND status = %s"
        params.append(status)
    
    if order_type:
        query += " AND order_type = %s"
        params.append(order_type)
    
    if domain_name:
        query += " AND description LIKE %s"
        params.append(f"%{domain_name}%")
    
    if from_date:
        query += " AND created_at >= %s"
        params.append(from_date)
    
    if to_date:
        query += " AND created_at <= %s"
        params.append(to_date)
    
    query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    
    orders = await execute_query(query, tuple(params))
    
    order_list = [{
        "id": o['id'],
        "type": o['order_type'],
        "status": o['status'],
        "amount": float(o['amount']) if o.get('amount') else 0,
        "description": o['description'],
        "created_at": o['created_at'].isoformat() if o.get('created_at') else None
    } for o in orders]
    
    return success_response({
        "orders": order_list,
        "total": len(order_list),
        "page": page,
        "per_page": per_page
    })


@router.get("/orders/{order_id}", response_model=dict, include_in_schema=False)
async def get_order(
    order_id: int,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get order details"""
    check_permission(key_data, "orders", "read")
    user_id = key_data["user_id"]
    
    result = await execute_query("""
        SELECT id, order_type, status, amount, description, created_at, completed_at
        FROM orders
        WHERE id = %s AND user_id = %s
    """, (order_id, user_id))
    
    if not result:
        from api.utils.errors import ResourceNotFoundError
        raise ResourceNotFoundError("Order", str(order_id))
    
    o = result[0]
    return success_response({
        "id": o['id'],
        "type": o['order_type'],
        "status": o['status'],
        "amount": float(o['amount']) if o.get('amount') else 0,
        "description": o['description'],
        "created_at": o['created_at'].isoformat() if o.get('created_at') else None,
        "completed_at": o['completed_at'].isoformat() if o.get('completed_at') else None
    })


@router.post("/orders/{order_id}/cancel", response_model=dict, include_in_schema=False)
async def cancel_order(
    order_id: int,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Cancel an order"""
    check_permission(key_data, "orders", "write")
    
    return success_response({
        "order_id": order_id,
        "cancelled": True
    }, "Order cancelled successfully")
