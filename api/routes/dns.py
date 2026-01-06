"""
DNS Management Routes
"""
import logging
from fastapi import APIRouter, Depends, Query
from api.middleware.authentication import get_api_key_from_header, check_permission
from api.schemas.dns import CreateDNSRecordRequest, UpdateDNSRecordRequest, BulkDNSRequest
from api.utils.responses import success_response
from api.utils.errors import ResourceNotFoundError, InternalServerError
from services.cloudflare import CloudflareService
from database import execute_query, get_dns_record_history, save_dns_record_history, update_single_dns_record_in_db, delete_single_dns_record_from_db

logger = logging.getLogger(__name__)
router = APIRouter()
cloudflare = CloudflareService()


@router.get("/domains/{domain_name}/dns/records", response_model=dict)
async def list_dns_records(
    domain_name: str,
    record_type: str = Query(None, regex="^(A|AAAA|CNAME|MX|TXT|NS|SRV)$"),
    key_data: dict = Depends(get_api_key_from_header)
):
    """List DNS records for a domain"""
    check_permission(key_data, "dns", "read")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT cloudflare_zone_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result or not domain_result[0]['cloudflare_zone_id']:
        raise ResourceNotFoundError("Domain or Cloudflare zone", domain_name)
    
    zone_id = domain_result[0]['cloudflare_zone_id']
    records = await cloudflare.list_dns_records(zone_id, record_type)
    
    return success_response({"records": records, "total": len(records)})


@router.get("/domains/{domain_name}/dns/records/{record_id}", response_model=dict)
async def get_dns_record(
    domain_name: str,
    record_id: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get a specific DNS record"""
    check_permission(key_data, "dns", "read")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT cloudflare_zone_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result or not domain_result[0]['cloudflare_zone_id']:
        raise ResourceNotFoundError("Domain", domain_name)
    
    zone_id = domain_result[0]['cloudflare_zone_id']
    record = await cloudflare.get_dns_record(zone_id, record_id)
    
    if not record:
        raise ResourceNotFoundError("DNS record", record_id)
    
    return success_response(record)


@router.post("/domains/{domain_name}/dns/records", response_model=dict)
async def create_dns_record(
    domain_name: str,
    request: CreateDNSRecordRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Create a new DNS record"""
    check_permission(key_data, "dns", "write")
    user_id = key_data["user_id"]
    
    request.validate_priority_required()
    
    domain_result = await execute_query("""
        SELECT cloudflare_zone_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result or not domain_result[0]['cloudflare_zone_id']:
        raise ResourceNotFoundError("Domain", domain_name)
    
    zone_id = domain_result[0]['cloudflare_zone_id']
    result = await cloudflare.create_dns_record(
        zone_id=zone_id,
        record_type=request.type,
        name=request.name,
        content=request.content,
        ttl=request.ttl,
        priority=request.priority,
        weight=request.weight,
        port=request.port,
        proxied=request.proxied
    )
    
    if not result.get('success'):
        raise InternalServerError("DNS record creation failed", result.get('errors', []))
    
    # Track DNS change in history
    record_data = result.get('result', {})
    await save_dns_record_history(
        domain_name=domain_name,
        record_type=request.type,
        name=request.name,
        content=request.content,
        action='create',
        user_id=user_id,
        ttl=request.ttl,
        priority=request.priority,
        cloudflare_record_id=record_data.get('id')
    )
    
    # Sync record to database for dashboard display
    if record_data:
        try:
            await update_single_dns_record_in_db(domain_name, record_data)
            logger.info(f"✅ API DNS CREATE: Synced record to database for {domain_name}")
        except Exception as e:
            logger.warning(f"Failed to sync DNS record to database: {e}")
    
    return success_response(result.get('result', {}), "DNS record created successfully")


@router.put("/domains/{domain_name}/dns/records/{record_id}", response_model=dict)
async def update_dns_record(
    domain_name: str,
    record_id: str,
    request: UpdateDNSRecordRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Update a DNS record"""
    check_permission(key_data, "dns", "write")
    user_id = key_data["user_id"]
    
    request.validate_priority_required()
    
    domain_result = await execute_query("""
        SELECT cloudflare_zone_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result or not domain_result[0]['cloudflare_zone_id']:
        raise ResourceNotFoundError("Domain", domain_name)
    
    zone_id = domain_result[0]['cloudflare_zone_id']
    
    # Get old record data before updating
    old_record = await cloudflare.get_dns_record(zone_id, record_id)
    
    result = await cloudflare.update_dns_record(
        zone_id=zone_id,
        record_id=record_id,
        record_type=request.type,
        name=request.name,
        content=request.content,
        ttl=request.ttl,
        priority=request.priority,
        weight=request.weight,
        port=request.port,
        proxied=request.proxied
    )
    
    if not result.get('success'):
        raise InternalServerError("DNS record update failed", result.get('errors', []))
    
    # Track DNS change in history
    if old_record:
        await save_dns_record_history(
            domain_name=domain_name,
            record_type=request.type,
            name=request.name,
            content=request.content,
            action='update',
            user_id=user_id,
            ttl=request.ttl,
            priority=request.priority,
            cloudflare_record_id=record_id,
            old_content=old_record.get('content'),
            old_ttl=old_record.get('ttl'),
            old_priority=old_record.get('priority')
        )
    
    # Sync updated record to database for dashboard display
    record_data = result.get('result', {})
    if record_data:
        try:
            await update_single_dns_record_in_db(domain_name, record_data)
            logger.info(f"✅ API DNS UPDATE: Synced record to database for {domain_name}")
        except Exception as e:
            logger.warning(f"Failed to sync DNS record to database: {e}")
    
    return success_response(result.get('result', {}), "DNS record updated successfully")


@router.delete("/domains/{domain_name}/dns/records/{record_id}", response_model=dict)
async def delete_dns_record(
    domain_name: str,
    record_id: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Delete a DNS record"""
    check_permission(key_data, "dns", "write")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT cloudflare_zone_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result or not domain_result[0]['cloudflare_zone_id']:
        raise ResourceNotFoundError("Domain", domain_name)
    
    zone_id = domain_result[0]['cloudflare_zone_id']
    
    # Get record data before deleting
    old_record = await cloudflare.get_dns_record(zone_id, record_id)
    
    success = await cloudflare.delete_dns_record(zone_id, record_id)
    
    if not success:
        raise InternalServerError("DNS record deletion failed")
    
    # Track DNS change in history
    if old_record:
        await save_dns_record_history(
            domain_name=domain_name,
            record_type=old_record.get('type', 'UNKNOWN'),
            name=old_record.get('name', ''),
            content=old_record.get('content', ''),
            action='delete',
            user_id=user_id,
            ttl=old_record.get('ttl'),
            priority=old_record.get('priority'),
            cloudflare_record_id=record_id,
            old_content=old_record.get('content'),
            old_ttl=old_record.get('ttl'),
            old_priority=old_record.get('priority')
        )
    
    # Remove record from database for dashboard display
    try:
        await delete_single_dns_record_from_db(record_id)
        logger.info(f"✅ API DNS DELETE: Removed record from database for {domain_name}")
    except Exception as e:
        logger.warning(f"Failed to remove DNS record from database: {e}")
    
    return success_response({"deleted": True}, "DNS record deleted successfully")


@router.patch("/domains/{domain_name}/dns/records/{record_id}/proxy", response_model=dict)
async def toggle_proxy(
    domain_name: str,
    record_id: str,
    proxied: bool,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Toggle Cloudflare proxy for a DNS record"""
    check_permission(key_data, "dns", "write")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT cloudflare_zone_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result or not domain_result[0]['cloudflare_zone_id']:
        raise ResourceNotFoundError("Domain", domain_name)
    
    zone_id = domain_result[0]['cloudflare_zone_id']
    
    record = await cloudflare.get_dns_record(zone_id, record_id)
    if not record:
        raise ResourceNotFoundError("DNS record", record_id)
    
    result = await cloudflare.update_dns_record(
        zone_id=zone_id,
        record_id=record_id,
        record_type=record.get('type'),
        name=record.get('name'),
        content=record.get('content'),
        ttl=record.get('ttl', 1),
        priority=record.get('priority'),
        proxied=proxied
    )
    
    if not result.get('success'):
        raise InternalServerError("Failed to toggle proxy setting", result.get('errors', []))
    
    # Sync updated record to database for dashboard display
    record_data = result.get('result', {})
    if record_data:
        try:
            await update_single_dns_record_in_db(domain_name, record_data)
            logger.info(f"✅ API DNS PROXY TOGGLE: Synced record to database for {domain_name}")
        except Exception as e:
            logger.warning(f"Failed to sync DNS record to database: {e}")
    
    return success_response({
        "record_id": record_id,
        "proxied": proxied
    }, "Proxy setting updated successfully")


@router.post("/domains/{domain_name}/dns/records/bulk", response_model=dict)
async def bulk_dns_operations(
    domain_name: str,
    request: BulkDNSRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Perform bulk DNS operations (create, update, delete)"""
    check_permission(key_data, "dns", "write")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT cloudflare_zone_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result or not domain_result[0]['cloudflare_zone_id']:
        raise ResourceNotFoundError("Domain", domain_name)
    
    zone_id = domain_result[0]['cloudflare_zone_id']
    
    results = []
    for op in request.operations:
        try:
            if op.action == "create":
                result = await cloudflare.create_dns_record(
                    zone_id=zone_id,
                    record_type=op.type,
                    name=op.name,
                    content=op.content,
                    ttl=op.ttl or 1,
                    priority=op.priority,
                    proxied=op.proxied or False
                )
                record_data = result.get('result', {})
                results.append({
                    "action": "create",
                    "success": result.get('success', False),
                    "record": record_data
                })
                # Sync to database
                if result.get('success') and record_data:
                    try:
                        await update_single_dns_record_in_db(domain_name, record_data)
                    except Exception:
                        pass
            elif op.action == "update":
                result = await cloudflare.update_dns_record(
                    zone_id=zone_id,
                    record_id=op.record_id,
                    record_type=op.type,
                    name=op.name,
                    content=op.content,
                    ttl=op.ttl or 1,
                    priority=op.priority,
                    proxied=op.proxied or False
                )
                record_data = result.get('result', {})
                results.append({
                    "action": "update",
                    "success": result.get('success', False),
                    "record_id": op.record_id
                })
                # Sync to database
                if result.get('success') and record_data:
                    try:
                        await update_single_dns_record_in_db(domain_name, record_data)
                    except Exception:
                        pass
            elif op.action == "delete":
                success = await cloudflare.delete_dns_record(zone_id, op.record_id)
                results.append({
                    "action": "delete",
                    "success": success,
                    "record_id": op.record_id
                })
                # Remove from database
                if success:
                    try:
                        await delete_single_dns_record_from_db(op.record_id)
                    except Exception:
                        pass
            else:
                results.append({
                    "action": op.action,
                    "success": False,
                    "error": f"Unknown action: {op.action}"
                })
        except Exception as e:
            results.append({
                "action": op.action,
                "success": False,
                "error": str(e)
            })
    
    successful = sum(1 for r in results if r.get('success'))
    failed = len(results) - successful
    
    return success_response({
        "results": results,
        "total": len(results),
        "successful": successful,
        "failed": failed
    })


@router.get("/domains/{domain_name}/dns/export", response_model=dict)
async def export_dns_records(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Export all DNS records for a domain"""
    check_permission(key_data, "dns", "read")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT cloudflare_zone_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result or not domain_result[0]['cloudflare_zone_id']:
        raise ResourceNotFoundError("Domain", domain_name)
    
    zone_id = domain_result[0]['cloudflare_zone_id']
    records = await cloudflare.list_dns_records(zone_id, None)
    
    return success_response({
        "domain": domain_name,
        "records": records,
        "total": len(records),
        "format": "json"
    })


@router.get("/dns/supported-types", response_model=dict)
async def get_supported_types(
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get supported DNS record types"""
    check_permission(key_data, "dns", "read")
    
    types = cloudflare.get_supported_record_types()
    return success_response({"types": types})


@router.post("/domains/bulk-dns", response_model=dict)
async def bulk_dns_cross_domains(
    request: dict,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Apply DNS changes across multiple domains"""
    check_permission(key_data, "dns", "write")
    user_id = key_data["user_id"]
    
    domains = request.get('domains', [])
    dns_records = request.get('records', [])
    
    if not domains or not dns_records:
        raise InternalServerError("Both domains and records are required")
    
    results = []
    for domain_name in domains:
        domain_result = await execute_query("""
            SELECT cloudflare_zone_id FROM domains WHERE domain_name = %s AND user_id = %s
        """, (domain_name, user_id))
        
        if not domain_result or not domain_result[0]['cloudflare_zone_id']:
            results.append({
                "domain": domain_name,
                "success": False,
                "error": "Domain not found or no Cloudflare zone"
            })
            continue
        
        zone_id = domain_result[0]['cloudflare_zone_id']
        domain_results = []
        
        for record in dns_records:
            try:
                result = await cloudflare.create_dns_record(
                    zone_id=zone_id,
                    record_type=record.get('type'),
                    name=record.get('name'),
                    content=record.get('content'),
                    ttl=record.get('ttl', 1),
                    priority=record.get('priority'),
                    proxied=record.get('proxied', False)
                )
                record_data = result.get('result', {})
                domain_results.append({
                    "type": record.get('type'),
                    "name": record.get('name'),
                    "success": result.get('success', False)
                })
                # Sync to database
                if result.get('success') and record_data:
                    try:
                        await update_single_dns_record_in_db(domain_name, record_data)
                    except Exception:
                        pass
            except Exception as e:
                domain_results.append({
                    "type": record.get('type'),
                    "name": record.get('name'),
                    "success": False,
                    "error": str(e)
                })
        
        results.append({
            "domain": domain_name,
            "records": domain_results,
            "successful": sum(1 for r in domain_results if r.get('success'))
        })
    
    total_processed = sum(r.get('successful', 0) for r in results)
    
    return success_response({
        "results": results,
        "total_domains": len(domains),
        "total_records_processed": total_processed
    })


@router.get("/domains/{domain_name}/dns/history", response_model=dict)
async def get_dns_history(
    domain_name: str,
    record_type: str = Query(None, description="Filter by DNS record type (A, CNAME, MX, TXT, etc.)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of history records to return"),
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Get DNS record change history for a domain.
    
    Returns a chronological list of all DNS record changes (create, update, delete)
    for the specified domain. This provides an audit trail of DNS modifications.
    
    **Query Parameters:**
    - `record_type` (optional): Filter by DNS record type (A, CNAME, MX, TXT, etc.)
    - `limit` (optional): Maximum records to return (1-1000, default: 100)
    
    **Response Format:**
    ```json
    {
      "success": true,
      "message": "Retrieved X DNS history records for example.com",
      "data": {
        "domain": "example.com",
        "history": [
          {
            "id": 123,
            "record_type": "A",
            "name": "www",
            "action": "update",
            "old_value": "1.2.3.4",
            "new_value": "5.6.7.8",
            "ttl": 3600,
            "priority": null,
            "changed_by_user_id": 456,
            "changed_at": "2025-11-21T10:30:00Z",
            "metadata": {"source": "api"}
          }
        ],
        "total": 1,
        "filtered_by_type": "A"
      }
    }
    ```
    
    **Use Cases:**
    - Audit trail: Track who made changes and when
    - Troubleshooting: Review recent DNS modifications
    - Compliance: Maintain change logs for security
    - Rollback reference: See previous record values
    
    **Note:** This is a local tracking system since OpenProvider doesn't provide DNS history via API.
    Only changes made through this system are tracked.
    """
    check_permission(key_data, "dns", "read")
    user_id = key_data["user_id"]
    
    # Verify domain ownership
    domain_result = await execute_query("""
        SELECT id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    # Get DNS history
    history = await get_dns_record_history(domain_name, record_type, limit)
    
    return success_response({
        "domain": domain_name,
        "history": history,
        "total": len(history),
        "filtered_by_type": record_type
    }, f"Retrieved {len(history)} DNS history records for {domain_name}")
