"""
Nameserver Management Routes
"""
from fastapi import APIRouter, Depends, HTTPException
from api.middleware.authentication import get_api_key_from_header, check_permission
from api.schemas.nameserver import UpdateNameserversRequest
from api.utils.responses import success_response
from api.utils.errors import ResourceNotFoundError, InternalServerError
from services.openprovider import OpenProviderService
from handlers import get_hosting_nameservers
from database import execute_query
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
openprovider = OpenProviderService()


def map_openprovider_error_to_http_exception(result: dict, domain_name: str) -> HTTPException:
    """
    Map OpenProvider service errors to appropriate HTTP exceptions with detailed info.
    
    This function translates the rich error metadata from OpenProvider (error codes,
    user guidance, retry hints) into FastAPI HTTPException responses with proper
    HTTP status codes and actionable error messages.
    """
    error_type = result.get('error', 'UNKNOWN_ERROR')
    error_code = result.get('error_code')
    message = result.get('message', 'Nameserver update failed')
    user_action = result.get('user_action')
    technical_details = result.get('technical_details', result.get('details'))
    retry_suggested = result.get('retry_suggested', False)
    retry_delay = result.get('retry_delay_seconds')
    
    # Log the full error for observability before transforming
    logger.error(f"OpenProvider nameserver update failed for {domain_name}")
    logger.error(f"  Error Type: {error_type}")
    logger.error(f"  Error Code: {error_code}")
    logger.error(f"  Message: {message}")
    logger.error(f"  Technical Details: {technical_details}")
    logger.error(f"  Full Result: {result}")
    
    # Build error response payload
    error_payload = {
        "error_type": error_type,
        "message": message,
        "domain": domain_name
    }
    
    if error_code:
        error_payload["error_code"] = error_code
    if user_action:
        error_payload["user_action"] = user_action
    if technical_details:
        error_payload["technical_details"] = technical_details
    if retry_suggested:
        error_payload["retry_suggested"] = retry_suggested
    if retry_delay:
        error_payload["retry_after_seconds"] = retry_delay
    
    # Map error types to appropriate HTTP status codes
    
    # Glue record resolution failed (422 Unprocessable Entity)
    if error_type == 'GLUE_RECORD_RESOLUTION_FAILED':
        return HTTPException(
            status_code=422,
            detail=error_payload
        )
    
    # Domain status prohibited (409 Conflict or 423 Locked)
    if error_type in ['DOMAIN_STATUS_PROHIBITED', 'DOMAIN_STATUS_PROHIBITED_366'] or error_type.startswith('DOMAIN_OPERATION_PROHIBITED_'):
        return HTTPException(
            status_code=409,  # Conflict - domain state prevents operation
            detail=error_payload
        )
    
    # Domain in transitional state (409 Conflict with retry hint)
    if error_type == 'DOMAIN_STATUS_TRANSITIONAL':
        return HTTPException(
            status_code=409,
            detail=error_payload
        )
    
    # Temporary/transient errors (502 Bad Gateway or 503 Service Unavailable)
    if error_type.startswith('TEMPORARY_ERROR_') or error_code in [500, 503, 504]:
        return HTTPException(
            status_code=502,  # Bad Gateway - upstream provider issue
            detail=error_payload
        )
    
    # Rate limiting (429 Too Many Requests)
    if error_code == 429:
        return HTTPException(
            status_code=429,
            detail=error_payload
        )
    
    # Domain status check failed (503 Service Unavailable)
    if error_type == 'DOMAIN_STATUS_CHECK_FAILED':
        return HTTPException(
            status_code=503,
            detail=error_payload
        )
    
    # Generic domain update failures (400 Bad Request or 422 Unprocessable)
    if error_type.startswith('DOMAIN_UPDATE_FAILED_'):
        return HTTPException(
            status_code=422,
            detail=error_payload
        )
    
    # DENIC NS consistency errors (422 Unprocessable Entity)
    if error_type == 'DENIC_NS_CONSISTENCY_ERROR':
        return HTTPException(
            status_code=422,
            detail=error_payload
        )
    
    # OpenProvider error code 245: Invalid nameserver values (422 Unprocessable Entity)
    if error_code == 245:
        error_payload["message"] = f"Invalid nameserver values for {domain_name}. Nameservers must be valid hostnames (e.g., ns1.example.com, ns2.example.com)."
        error_payload["user_action"] = "Please provide valid nameserver hostnames. Each nameserver must be a fully qualified domain name (FQDN) that can be resolved via DNS."
        return HTTPException(
            status_code=422,
            detail=error_payload
        )
    
    # HTTP 500 errors from OpenProvider (502 Bad Gateway - upstream issue)
    if error_type == 'HTTP_ERROR_500':
        # Check if this is actually a validation error based on context
        if 'nameserver' in message.lower():
            error_payload["message"] = f"Invalid nameserver configuration for {domain_name}. The nameserver values provided are not valid."
            error_payload["user_action"] = "Please provide valid nameserver hostnames (e.g., ns1.example.com, ns2.example.com). Do not use placeholder values like 'string'."
            return HTTPException(
                status_code=422,
                detail=error_payload
            )
        # Otherwise treat as upstream error
        return HTTPException(
            status_code=502,
            detail=error_payload
        )
    
    # Default: Internal Server Error for unexpected failures
    return HTTPException(
        status_code=500,
        detail=error_payload
    )


@router.get("/domains/{domain_name}/nameservers", response_model=dict)
async def get_nameservers(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get current nameservers for a domain"""
    check_permission(key_data, "nameservers", "read")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT provider_domain_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    openprovider_id = domain_result[0]['provider_domain_id']
    
    domain_info = await openprovider.get_domain_info(openprovider_id)
    nameservers = domain_info.get('nameservers', []) if domain_info else []
    
    is_cloudflare = any('cloudflare' in ns.lower() for ns in nameservers)
    
    return success_response({
        "domain": domain_name,
        "nameservers": nameservers,
        "provider": "cloudflare" if is_cloudflare else "custom",
        "provider_name": "Cloudflare DNS" if is_cloudflare else "Custom Nameservers",
        "is_cloudflare": is_cloudflare,
        "last_updated": domain_info.get('updated_at') if domain_info else None
    })


@router.put("/domains/{domain_name}/nameservers", response_model=dict)
async def update_nameservers(
    domain_name: str,
    request: UpdateNameserversRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Update nameservers for a domain with automatic glue record support.
    
    This endpoint updates the authoritative nameservers for your domain via OpenProvider.
    It automatically detects and handles child nameservers (glue records) by resolving
    their IP addresses when needed.
    
    **Child Nameserver (Glue Record) Support:**
    
    When you use nameservers that are subdomains of the domain being updated (e.g.,
    ns1.example.com for example.com), the system automatically:
    
    1. Detects that these are child nameservers (glue records)
    2. Resolves their IPv4 and IPv6 addresses via DNS
    3. Includes the IP addresses in the OpenProvider API request
    4. Ensures proper DNS delegation without circular dependencies
    
    **Example Use Cases:**
    
    Standard nameservers (no glue records needed):
    ```json
    {
      "nameservers": [
        "anderson.ns.cloudflare.com",
        "leanna.ns.cloudflare.com"
      ]
    }
    ```
    
    Child nameservers (glue records automatically handled):
    ```json
    {
      "nameservers": [
        "ns1.example.com",
        "ns2.example.com"
      ]
    }
    ```
    In this case, the system will:
    - Detect that ns1.example.com is a subdomain of example.com
    - Resolve ns1.example.com to its IP address (e.g., 192.0.2.1)
    - Send the IP as a glue record to OpenProvider
    - Enable proper DNS delegation
    
    **Important Notes:**
    - Glue records are only needed when nameservers are subdomains of the domain being updated
    - External nameservers (e.g., Cloudflare, Google DNS) don't need glue records
    - IP resolution happens automatically - you don't need to provide IPs manually
    - The system supports both IPv4 and IPv6 glue records
    - Changes may take 24-48 hours to fully propagate across DNS servers
    
    **Error Handling:**
    - If glue record IP resolution fails, you'll receive a 422 error with details
    - Make sure child nameservers have valid DNS A/AAAA records before updating
    """
    check_permission(key_data, "nameservers", "write")
    user_id = key_data["user_id"]
    
    # Log what we received from the client
    logger.info(f"📥 API RECEIVED nameserver update request for {domain_name}")
    logger.info(f"   Nameservers from request: {request.nameservers}")
    
    # Validate: Reject literal "string" placeholder values from Swagger UI
    if any(ns.lower() == "string" for ns in request.nameservers):
        raise HTTPException(
            status_code=400,
            detail={
                "error_type": "INVALID_INPUT",
                "message": "Placeholder values detected. Please replace 'string' with actual nameserver hostnames.",
                "user_action": "In the Swagger UI JSON editor, replace the entire array with your actual nameservers. Example: [\"anderson.ns.cloudflare.com\", \"leanna.ns.cloudflare.com\"]",
                "swagger_ui_tip": "Click in the nameservers field, delete everything, and type your actual JSON array with real nameserver hostnames.",
                "provided_values": request.nameservers
            }
        )
    
    domain_result = await execute_query("""
        SELECT provider_domain_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    result = await openprovider.update_nameservers(domain_name, request.nameservers)
    
    if not result:
        logger.error(f"OpenProvider returned None for nameserver update: {domain_name}")
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": "OPENPROVIDER_NO_RESPONSE",
                "message": "No response from domain registrar",
                "domain": domain_name
            }
        )
    
    if not result.get('success'):
        raise map_openprovider_error_to_http_exception(result, domain_name)
    
    return success_response({
        "domain": domain_name,
        "nameservers": request.nameservers,
        "updated": True
    }, "Nameservers updated successfully (may take 24-48 hours to propagate)")


@router.post("/domains/{domain_name}/nameservers/cloudflare", response_model=dict)
async def set_cloudflare_nameservers(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Set nameservers to Cloudflare automatically"""
    check_permission(key_data, "nameservers", "write")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT cloudflare_zone_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result or not domain_result[0][0]:
        raise ResourceNotFoundError("Cloudflare zone", domain_name)
    
    cf_nameservers = ["anderson.ns.cloudflare.com", "leanna.ns.cloudflare.com"]
    
    result = await openprovider.update_nameservers(domain_name, cf_nameservers)
    
    if not result:
        logger.error(f"OpenProvider returned None for Cloudflare nameserver update: {domain_name}")
        raise HTTPException(status_code=500, detail={
            "error_type": "OPENPROVIDER_NO_RESPONSE",
            "message": "No response from domain registrar",
            "domain": domain_name
        })
    
    if not result.get('success'):
        raise map_openprovider_error_to_http_exception(result, domain_name)
    
    return success_response({
        "domain": domain_name,
        "nameservers": cf_nameservers,
        "provider": "cloudflare"
    })


@router.post("/domains/{domain_name}/nameservers/hosting", response_model=dict)
async def set_hosting_nameservers(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Set nameservers to hosting nameservers"""
    check_permission(key_data, "nameservers", "write")
    
    hosting_ns = get_hosting_nameservers()
    
    result = await openprovider.update_nameservers(domain_name, hosting_ns)
    
    if not result:
        logger.error(f"OpenProvider returned None for hosting nameserver update: {domain_name}")
        raise HTTPException(status_code=500, detail={
            "error_type": "OPENPROVIDER_NO_RESPONSE",
            "message": "No response from domain registrar",
            "domain": domain_name
        })
    
    if not result.get('success'):
        raise map_openprovider_error_to_http_exception(result, domain_name)
    
    return success_response({
        "domain": domain_name,
        "nameservers": hosting_ns,
        "provider": "hosting"
    })


@router.get("/domains/{domain_name}/nameservers/analyze", response_model=dict)
async def analyze_nameservers(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Analyze domain nameserver configuration"""
    check_permission(key_data, "nameservers", "read")
    user_id = key_data["user_id"]
    
    domain_result = await execute_query("""
        SELECT provider_domain_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    openprovider_id = domain_result[0]['provider_domain_id']
    
    domain_info = await openprovider.get_domain_info(openprovider_id)
    nameservers = domain_info.get('nameservers', []) if domain_info else []
    
    is_cloudflare = any('cloudflare' in ns.lower() for ns in nameservers)
    is_hosting = any('hostbay' in ns.lower() or 'cpanel' in ns.lower() for ns in nameservers)
    
    recommendations = []
    if len(nameservers) < 2:
        recommendations.append("Add at least 2 nameservers for redundancy")
    elif len(nameservers) >= 2:
        recommendations.append("Nameserver configuration looks good")
    
    if is_cloudflare:
        provider = "cloudflare"
        is_ready = True
        recommendations.append("Using Cloudflare nameservers - DNS management available")
    elif is_hosting:
        provider = "hosting"
        is_ready = True
        recommendations.append("Using hosting nameservers - ready for cPanel")
    else:
        provider = "custom"
        is_ready = False
        recommendations.append("Using custom nameservers - update to Cloudflare or hosting NS for full features")
    
    return success_response({
        "current_nameservers": nameservers,
        "provider": provider,
        "is_ready_for_hosting": is_ready,
        "is_cloudflare": is_cloudflare,
        "recommendations": recommendations
    })


@router.get("/domains/{domain_name}/nameservers/verify", response_model=dict)
async def verify_nameservers(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Verify nameserver propagation using DNS queries"""
    check_permission(key_data, "nameservers", "read")
    user_id = key_data["user_id"]
    
    from datetime import datetime, timezone
    import socket
    
    domain_result = await execute_query("""
        SELECT provider_domain_id FROM domains WHERE domain_name = %s AND user_id = %s
    """, (domain_name, user_id))
    
    if not domain_result:
        raise ResourceNotFoundError("Domain", domain_name)
    
    openprovider_id = domain_result[0]['provider_domain_id']
    
    domain_info = await openprovider.get_domain_info(openprovider_id)
    expected_nameservers = domain_info.get('nameservers', []) if domain_info else []
    
    try:
        import dns.resolver
        resolver = dns.resolver.Resolver()
        resolver.timeout = 5
        resolver.lifetime = 10
        
        answers = resolver.resolve(domain_name, 'NS')
        detected_nameservers = [str(rdata.target).rstrip('.') for rdata in answers]
        
        matches = set(ns.lower() for ns in expected_nameservers) == set(ns.lower() for ns in detected_nameservers)
        propagated = len(detected_nameservers) > 0 and matches
        
    except Exception as e:
        logger.warning(f"DNS query failed for {domain_name}: {e}")
        detected_nameservers = []
        matches = False
        propagated = False
    
    return success_response({
        "propagated": propagated,
        "nameservers_detected": detected_nameservers,
        "nameservers_expected": expected_nameservers,
        "matches_expected": matches,
        "check_timestamp": datetime.now(timezone.utc).isoformat()
    })


@router.get("/nameservers/presets", response_model=dict)
async def get_nameserver_presets(
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get available nameserver presets"""
    check_permission(key_data, "nameservers", "read")
    
    hosting_ns = get_hosting_nameservers()
    
    return success_response({
        "cloudflare": ["anderson.ns.cloudflare.com", "leanna.ns.cloudflare.com"],
        "hosting": hosting_ns
    })
