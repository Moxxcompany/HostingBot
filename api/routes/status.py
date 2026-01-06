"""
Status tracking routes for hosting provision intents and bulk operations.
"""
from fastapi import APIRouter, Depends
from api.middleware.authentication import get_api_key_from_header, check_permission
from api.schemas.status import (
    HostingProvisionIntentResponse, 
    BulkDomainStatusRequest,
    BulkHostingStatusRequest,
    DomainTransferStatusResponse,
    BulkOperationResponse,
    DomainRegistrationHistoryResponse
)
from api.utils.responses import success_response
from api.utils.errors import ResourceNotFoundError
from database import execute_query

router = APIRouter()


@router.get("/hosting/intents/{intent_id}", response_model=dict)
async def get_hosting_intent_status(
    intent_id: int,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Get hosting provision intent status.
    
    Queries the hosting_provision_intents table and returns the current status
    of a hosting provision request. Only returns intents that belong to the
    authenticated user.
    
    Args:
        intent_id: The hosting provision intent ID
        key_data: API key authentication data
    
    Returns:
        HostingProvisionIntentResponse with status details
    
    Raises:
        ResourceNotFoundError: If intent not found or doesn't belong to user
    """
    check_permission(key_data, "hosting", "read")
    user_id = key_data["user_id"]
    
    result = await execute_query("""
        SELECT id, status, domain_name, service_type, quote_price, currency,
               error_message, processing_started_at, completed_at, created_at, 
               updated_at, user_id
        FROM hosting_provision_intents
        WHERE id = %s
    """, (intent_id,))
    
    if not result:
        raise ResourceNotFoundError("Hosting provision intent", str(intent_id))
    
    intent = result[0]
    
    if intent['user_id'] != user_id:
        raise ResourceNotFoundError("Hosting provision intent", str(intent_id))
    
    def format_timestamp(ts):
        """Format timestamp as ISO 8601 with 'Z' suffix"""
        if ts is None:
            return None
        if isinstance(ts, str):
            return ts if ts.endswith('Z') else f"{ts}Z"
        return ts.isoformat().replace('+00:00', 'Z') if ts else None
    
    response_data = {
        "intent_id": intent['id'],
        "status": intent['status'],
        "domain_name": intent.get('domain_name'),
        "service_type": intent['service_type'],
        "quote_price": float(intent['quote_price']) if intent.get('quote_price') is not None else None,
        "currency": intent.get('currency', 'USD'),
        "error_message": intent.get('error_message'),
        "processing_started_at": format_timestamp(intent.get('processing_started_at')),
        "completed_at": format_timestamp(intent.get('completed_at')),
        "created_at": format_timestamp(intent['created_at']),
        "updated_at": format_timestamp(intent['updated_at'])
    }
    
    return success_response(response_data)


@router.post("/domains/bulk-status", response_model=dict)
async def bulk_domain_status(
    request: BulkDomainStatusRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Get status for multiple domains in a single request.
    
    Checks the status of up to 100 domains at once. Returns partial results
    if some domains are not found in the database. Only returns domains that
    belong to the authenticated user.
    
    Args:
        request: BulkDomainStatusRequest with list of domain names
        key_data: API key authentication data
    
    Returns:
        BulkDomainStatusResponse with domain status information
    """
    check_permission(key_data, "domains", "read")
    user_id = key_data["user_id"]
    
    domains_list = request.domains
    total = len(domains_list)
    
    if not domains_list:
        return success_response({
            "results": [],
            "total": 0,
            "found": 0,
            "not_found": 0
        })
    
    placeholders = ', '.join(['%s'] * len(domains_list))
    query = f"""
        SELECT domain_name, status, cloudflare_zone_id
        FROM domains
        WHERE domain_name IN ({placeholders})
        AND user_id = %s
    """
    
    params = tuple(domains_list) + (user_id,)
    results = await execute_query(query, params)
    
    domain_status_list = []
    for row in results:
        domain_status_list.append({
            "domain": row['domain_name'],
            "status": row['status'],
            "dns_active": bool(row['cloudflare_zone_id']),
            "ssl_active": False,
            # New generic field name
            "dns_zone_id": row['cloudflare_zone_id'],
            # Legacy field name (backward compatibility)
            "cloudflare_zone_id": row['cloudflare_zone_id']
        })
    
    found = len(domain_status_list)
    not_found = total - found
    
    response_data = {
        "results": domain_status_list,
        "total": total,
        "found": found,
        "not_found": not_found
    }
    
    return success_response(response_data)


@router.post("/hosting/bulk-status", response_model=dict)
async def bulk_hosting_status(
    request: BulkHostingStatusRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Get status for multiple hosting subscriptions in a single request.
    
    Checks the status of up to 100 hosting subscriptions at once. Returns partial
    results if some subscriptions are not found in the database. Only returns
    subscriptions that belong to the authenticated user.
    
    Args:
        request: BulkHostingStatusRequest with list of subscription IDs
        key_data: API key authentication data
    
    Returns:
        BulkHostingStatusResponse with hosting subscription status information
    """
    check_permission(key_data, "hosting", "read")
    user_id = key_data["user_id"]
    
    subscription_ids = request.subscription_ids
    total = len(subscription_ids)
    
    if not subscription_ids:
        return success_response({
            "results": [],
            "total": 0,
            "found": 0,
            "not_found": 0
        })
    
    placeholders = ', '.join(['%s'] * len(subscription_ids))
    query = f"""
        SELECT hs.id, hs.domain_name, hp.plan_name, hs.status, hs.next_billing_date
        FROM hosting_subscriptions hs
        JOIN hosting_plans hp ON hs.hosting_plan_id = hp.id
        WHERE hs.id IN ({placeholders})
        AND hs.user_id = %s
    """
    
    params = tuple(subscription_ids) + (user_id,)
    results = await execute_query(query, params)
    
    def format_timestamp(ts):
        """Format timestamp as ISO 8601 with 'Z' suffix"""
        if ts is None:
            return None
        if isinstance(ts, str):
            return ts if ts.endswith('Z') else f"{ts}Z"
        return ts.isoformat().replace('+00:00', 'Z') if ts else None
    
    hosting_status_list = []
    for row in results:
        hosting_status_list.append({
            "id": row['id'],
            "domain_name": row['domain_name'],
            "plan": row['plan_name'],
            "status": row['status'],
            "is_active": row['status'] == "active",
            "expires_at": format_timestamp(row.get('next_billing_date'))
        })
    
    found = len(hosting_status_list)
    not_found = total - found
    
    response_data = {
        "results": hosting_status_list,
        "total": total,
        "found": found,
        "not_found": not_found
    }
    
    return success_response(response_data)


@router.get("/domains/{domain_name}/transfer/status", response_model=dict)
async def get_domain_transfer_status(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Get domain transfer status.
    
    Queries the domains table for transfer information. Only returns domains
    that belong to the authenticated user and have a transfer-related status.
    
    Args:
        domain_name: The domain name to check transfer status for
        key_data: API key authentication data
    
    Returns:
        DomainTransferStatusResponse with transfer status details
    
    Raises:
        ResourceNotFoundError: If domain not found or doesn't belong to user
    """
    check_permission(key_data, "domains", "read")
    user_id = key_data["user_id"]
    
    result = await execute_query("""
        SELECT domain_name, status, created_at, metadata
        FROM domains
        WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    domain = result[0]
    
    def format_timestamp(ts):
        """Format timestamp as ISO 8601 with 'Z' suffix"""
        if ts is None:
            return None
        if isinstance(ts, str):
            return ts if ts.endswith('Z') else f"{ts}Z"
        return ts.isoformat().replace('+00:00', 'Z') if ts else None
    
    status = domain['status']
    initiated_at = None
    
    if status and 'transfer' in status.lower():
        initiated_at = format_timestamp(domain.get('created_at'))
    
    response_data = {
        "domain_name": domain['domain_name'],
        "status": status,
        "initiated_at": initiated_at,
        "can_expedite": False,
        "days_remaining": None,
        "transfer_details": domain.get('metadata')
    }
    
    return success_response(response_data)


@router.get("/operations/{operation_id}", response_model=dict)
async def get_bulk_operation_status(
    operation_id: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Get bulk operation tracking status.
    
    Queries the bulk_operations table and returns the current status of a
    bulk operation. Only returns operations that belong to the authenticated user.
    
    Args:
        operation_id: The bulk operation ID
        key_data: API key authentication data
    
    Returns:
        BulkOperationResponse with operation status and results
    
    Raises:
        ResourceNotFoundError: If operation not found or doesn't belong to user
    """
    check_permission(key_data, "operations", "read")
    user_id = key_data["user_id"]
    
    result = await execute_query("""
        SELECT id, user_id, operation_type, status, total_items, completed,
               failed, pending, results, created_at, updated_at
        FROM bulk_operations
        WHERE id = %s
    """, (operation_id,))
    
    if not result:
        raise ResourceNotFoundError("Operation", operation_id)
    
    operation = result[0]
    
    if operation['user_id'] != user_id:
        raise ResourceNotFoundError("Operation", operation_id)
    
    def format_timestamp(ts):
        """Format timestamp as ISO 8601 with 'Z' suffix"""
        if ts is None:
            return None
        if isinstance(ts, str):
            return ts if ts.endswith('Z') else f"{ts}Z"
        return ts.isoformat().replace('+00:00', 'Z') if ts else None
    
    results = operation.get('results')
    if results and isinstance(results, dict):
        results_list = results.get('items', [])
    elif results and isinstance(results, list):
        results_list = results
    else:
        results_list = None
    
    response_data = {
        "operation_id": operation['id'],
        "operation_type": operation['operation_type'],
        "status": operation['status'],
        "total_items": operation['total_items'],
        "completed": operation['completed'],
        "failed": operation['failed'],
        "pending": operation['pending'],
        "created_at": format_timestamp(operation['created_at']),
        "updated_at": format_timestamp(operation['updated_at']),
        "results": results_list
    }
    
    return success_response(response_data)


@router.get("/domains/{domain_name}/registration-history", response_model=dict)
async def get_domain_registration_history(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Get domain registration history with all attempts.
    
    Queries the domain_registration_attempts table for all registration attempts
    for a specific domain. Returns all attempts that belong to the authenticated user.
    
    Args:
        domain_name: The domain name to get registration history for
        key_data: API key authentication data
    
    Returns:
        DomainRegistrationHistoryResponse with list of registration attempts
    """
    check_permission(key_data, "domains", "read")
    user_id = key_data["user_id"]
    
    results = await execute_query("""
        SELECT id, domain_name, status, error_message, openprovider_response,
               amount_charged, created_at
        FROM domain_registration_attempts
        WHERE domain_name = %s AND user_id = %s
        ORDER BY created_at DESC
    """, (domain_name, user_id))
    
    def format_timestamp(ts):
        """Format timestamp as ISO 8601 with 'Z' suffix"""
        if ts is None:
            return None
        if isinstance(ts, str):
            return ts if ts.endswith('Z') else f"{ts}Z"
        return ts.isoformat().replace('+00:00', 'Z') if ts else None
    
    attempts = []
    for row in results:
        attempts.append({
            "attempt_id": row['id'],
            "timestamp": format_timestamp(row['created_at']),
            "status": row['status'],
            "error_message": row.get('error_message'),
            # New generic field name
            "registry_response": row.get('openprovider_response'),
            # Legacy field name (backward compatibility)
            "openprovider_response": row.get('openprovider_response'),
            "amount_charged": float(row['amount_charged']) if row.get('amount_charged') is not None else None
        })
    
    last_attempt_at = None
    if attempts:
        last_attempt_at = attempts[0]['timestamp']
    
    response_data = {
        "domain_name": domain_name,
        "attempts": attempts,
        "total_attempts": len(attempts),
        "last_attempt_at": last_attempt_at
    }
    
    return success_response(response_data)
