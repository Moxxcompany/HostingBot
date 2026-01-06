"""
Domain Linking Routes
"""
from fastapi import APIRouter, Depends
from api.middleware.authentication import get_api_key_from_header, check_permission
from api.schemas.linking import (
    StartDomainLinkingRequest, 
    DNSInstructionsResponse,
    DomainStatus,
    NameserverMethod,
    ARecordMethod
)
from api.utils.responses import success_response
from api.utils.errors import ResourceNotFoundError, InternalServerError
from services.domain_linking_orchestrator import DomainLinkingOrchestrator
from services.domain_linking_config import CLOUDFLARE_NAMESERVERS
from services.domain_analysis_service import DomainAnalysisService
from services.cpanel import CPanelService
from services.cloudflare import CloudflareService
from database import execute_query

router = APIRouter()
linking_orchestrator = DomainLinkingOrchestrator()
domain_analysis_service = DomainAnalysisService()
cpanel_service = CPanelService()
cloudflare_service = CloudflareService()


@router.post("/domains/{domain_name}/link", response_model=dict)
async def start_domain_linking(
    domain_name: str,
    request: StartDomainLinkingRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Start domain linking workflow for external domain"""
    check_permission(key_data, "hosting", "write")
    user_id = key_data["user_id"]
    
    # Create linking intent via orchestrator
    result = await linking_orchestrator.create_linking_intent(
        user_id=user_id,
        domain_name=domain_name,
        hosting_subscription_id=None,
        intent_type=request.linking_mode
    )
    
    if not result.get('success'):
        raise InternalServerError("Failed to create domain linking intent", result)
    
    return success_response({
        "domain": domain_name,
        "linking_mode": request.linking_mode,
        "status": result.get('workflow_state'),
        "intent_id": result.get('intent_id'),
        "progress_percentage": result.get('progress_percentage', 0)
    }, "Domain linking workflow initiated")


@router.get("/domains/{domain_name}/link/status", response_model=dict)
async def get_linking_status(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get domain linking status"""
    check_permission(key_data, "hosting", "read")
    user_id = key_data["user_id"]
    
    # Get latest linking intent for this domain
    result = await execute_query("""
        SELECT id, workflow_state, current_step, progress_percentage, 
               intent_type, updated_at, estimated_completion_at
        FROM domain_link_intents
        WHERE domain_name = %s AND user_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (domain_name, user_id))
    
    if not result:
        raise ResourceNotFoundError("Domain linking intent", domain_name)
    
    intent = result[0]
    
    # Handle both dict and tuple results
    if isinstance(intent, dict):
        return success_response({
            "domain": domain_name,
            "status": intent['workflow_state'],
            "progress": intent['progress_percentage'],
            "current_step": intent['current_step'],
            "linking_mode": intent['intent_type'],
            "updated_at": intent['updated_at'].isoformat() + "Z" if intent.get('updated_at') else None,
            "estimated_completion": intent['estimated_completion_at'].isoformat() + "Z" if intent.get('estimated_completion_at') else None
        })
    else:
        return success_response({
            "domain": domain_name,
            "status": intent[1],
            "progress": intent[3],
            "current_step": intent[2],
            "linking_mode": intent[4],
            "updated_at": intent[5].isoformat() + "Z" if intent[5] else None,
            "estimated_completion": intent[6].isoformat() + "Z" if intent[6] else None
        })


@router.get("/domains/{domain_name}/link/instructions", response_model=dict)
async def get_linking_instructions(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get step-by-step linking instructions"""
    check_permission(key_data, "hosting", "read")
    user_id = key_data["user_id"]
    
    # Get latest linking intent
    result = await execute_query("""
        SELECT id, intent_type, configuration_data
        FROM domain_link_intents
        WHERE domain_name = %s AND user_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (domain_name, user_id))
    
    if not result:
        raise ResourceNotFoundError("Domain linking intent", domain_name)
    
    intent_data = result[0]
    intent_id = intent_data['id'] if isinstance(intent_data, dict) else intent_data[0]
    mode = intent_data['intent_type'] if isinstance(intent_data, dict) else intent_data[1]
    config_raw = intent_data['configuration_data'] if isinstance(intent_data, dict) else intent_data[2]
    
    # Decode JSON if stored as string
    import json
    config = json.loads(config_raw) if isinstance(config_raw, str) else (config_raw or {})
    
    # Get workflow status with user guidance
    status = await linking_orchestrator.get_user_workflow_status(user_id, intent_id)
    
    if not status.get('success'):
        raise InternalServerError("Failed to get linking instructions", status)
    
    return success_response({
        "mode": mode,
        "instructions": status.get('step_description', 'Follow the steps below'),
        "current_step": status.get('current_step_name', 'Setup'),
        "user_message": status.get('user_message', ''),
        "estimated_time": status.get('estimated_time', '24-48 hours')
    })


@router.post("/domains/{domain_name}/link/verify", response_model=dict)
async def verify_linking(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Manually trigger domain linking verification"""
    check_permission(key_data, "hosting", "write")
    user_id = key_data["user_id"]
    
    result = await execute_query("""
        SELECT id, intent_type FROM domain_link_intents
        WHERE domain_name = %s AND user_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (domain_name, user_id))
    
    if not result:
        raise ResourceNotFoundError("Domain linking intent", domain_name)
    
    intent_id = result[0]['id']
    intent_type = result[0]['intent_type']
    
    # User confirms they've completed the instructions, trigger verification
    confirmation_result = await linking_orchestrator.user_confirm_instructions(user_id, intent_id)
    
    if not confirmation_result.get('success'):
        raise InternalServerError("Verification initiation failed", confirmation_result)
    
    return success_response({
        "domain": domain_name,
        "verification_initiated": True,
        "verification_type": intent_type,
        "message": confirmation_result.get('message', 'Verification started')
    }, "Verification initiated - we'll check your domain configuration now")


@router.delete("/domains/{domain_name}/link", response_model=dict)
async def cancel_linking(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Cancel domain linking process"""
    check_permission(key_data, "hosting", "write")
    user_id = key_data["user_id"]
    
    from database import execute_update
    
    result = await execute_query("""
        SELECT id FROM domain_link_intents
        WHERE domain_name = %s AND user_id = %s AND workflow_state NOT IN ('completed', 'cancelled')
        ORDER BY created_at DESC
        LIMIT 1
    """, (domain_name, user_id))
    
    if not result:
        raise ResourceNotFoundError("Active domain linking intent", domain_name)
    
    intent_id = result[0]['id']
    
    await execute_update("""
        UPDATE domain_link_intents
        SET workflow_state = 'cancelled',
            updated_at = NOW()
        WHERE id = %s
    """, (intent_id,))
    
    return success_response({
        "domain": domain_name,
        "cancelled": True,
        "intent_id": intent_id
    }, "Domain linking cancelled")


@router.get("/domains/{domain_name}/link/history", response_model=dict)
async def get_linking_history(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get domain linking history"""
    check_permission(key_data, "hosting", "read")
    user_id = key_data["user_id"]
    
    result = await execute_query("""
        SELECT id, intent_type, workflow_state, progress_percentage, 
               created_at, updated_at, current_step
        FROM domain_link_intents
        WHERE domain_name = %s AND user_id = %s
        ORDER BY created_at DESC
        LIMIT 20
    """, (domain_name, user_id))
    
    # Handle both dict and tuple results
    history = []
    for h in result:
        if isinstance(h, dict):
            history.append({
                "intent_id": h['id'],
                "linking_mode": h['intent_type'],
                "status": h['workflow_state'],
                "progress": h['progress_percentage'],
                "created_at": h['created_at'].isoformat() + "Z" if h['created_at'] else None,
                "updated_at": h['updated_at'].isoformat() + "Z" if h['updated_at'] else None,
                "current_step": h['current_step']
            })
        else:
            history.append({
                "intent_id": h[0],
                "linking_mode": h[1],
                "status": h[2],
                "progress": h[3],
                "created_at": h[4].isoformat() + "Z" if h[4] else None,
                "updated_at": h[5].isoformat() + "Z" if h[5] else None,
                "current_step": h[6]
            })
    
    return success_response({
        "domain": domain_name,
        "history": history,
        "total": len(history)
    })


@router.post("/domains/{domain_name}/link/retry", response_model=dict)
async def retry_linking(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Retry failed domain linking"""
    check_permission(key_data, "hosting", "write")
    user_id = key_data["user_id"]
    
    from database import execute_update
    
    result = await execute_query("""
        SELECT id, intent_type FROM domain_link_intents
        WHERE domain_name = %s AND user_id = %s AND workflow_state = 'failed'
        ORDER BY created_at DESC
        LIMIT 1
    """, (domain_name, user_id))
    
    if not result:
        raise ResourceNotFoundError("Failed domain linking intent", domain_name)
    
    intent_id = result[0]['id']
    
    # Resume the intent from its current state
    resume_result = await linking_orchestrator.resume_intent(intent_id)
    
    if not resume_result.get('success'):
        raise InternalServerError("Failed to retry linking", resume_result)
    
    return success_response({
        "domain": domain_name,
        "retrying": True,
        "intent_id": intent_id,
        "message": resume_result.get('message', 'Linking workflow resumed')
    }, "Linking retry initiated")


@router.get("/linking/modes", response_model=dict)
async def get_linking_modes(
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get available linking modes"""
    check_permission(key_data, "hosting", "read")
    
    return success_response({
        "modes": [
            {
                "mode": "smart",
                "name": "Smart Mode (Automatic)",
                "description": "Automatically update nameservers - fast and simple",
                "recommended": True
            },
            {
                "mode": "manual",
                "name": "Manual Mode (DNS Records)",
                "description": "Keep existing nameservers, add DNS records - for complex setups",
                "recommended": False
            }
        ]
    })


@router.get("/domains/{domain_name}/link/dns-instructions", response_model=DNSInstructionsResponse, deprecated=True)
async def get_dns_instructions(
    domain_name: str,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    **DEPRECATED**: Use `GET /hosting/server-info?domain_name={domain}` instead.
    
    This endpoint functionality has been merged into the server-info endpoint.
    Pass domain_name as a query parameter to get the same DNS instructions.
    
    Get precise DNS configuration instructions for external domain linking.
    
    Returns both nameserver and A record methods with:
    - Cloudflare nameservers for the nameserver method
    - cPanel server IP for the A record method
    - Edge case detection (internal domains, already using Cloudflare)
    - Step-by-step instructions for each method
    """
    check_permission(key_data, "hosting", "read")
    user_id = key_data["user_id"]
    
    # Check if domain was purchased on HostBay platform (internal domain)
    internal_domain_check = await execute_query("""
        SELECT id, domain_name FROM domains 
        WHERE domain_name = %s AND user_id = %s AND deleted_at IS NULL
        LIMIT 1
    """, (domain_name.lower(), user_id))
    
    is_internal = len(internal_domain_check) > 0 if internal_domain_check else False
    
    # Analyze current domain DNS configuration using analyze_domain method
    analysis_result = await domain_analysis_service.analyze_domain(domain_name)
    dns_info = analysis_result.get('dns_info', {})
    current_nameservers = dns_info.get('nameservers', [])
    
    # Check if already using Cloudflare nameservers
    cloudflare_ns_patterns = ['cloudflare.com', 'cloudflare.net']
    already_using_cloudflare = any(
        any(cf_pattern in ns.lower() for cf_pattern in cloudflare_ns_patterns)
        for ns in current_nameservers
    )
    
    # Determine recommendation based on domain status
    if is_internal:
        recommendation_text = "This domain was purchased through HostBay. DNS is already configured - no changes needed."
    elif already_using_cloudflare:
        recommendation_text = "Domain already uses Cloudflare. Use the A Record method to point to our hosting server."
    else:
        recommendation_text = "Update nameservers to Cloudflare for full DNS management and automatic SSL."
    
    # Get cPanel server IP (dynamically detected)
    server_ip = cpanel_service.default_server_ip
    
    # Fetch HostBay Cloudflare account nameservers DYNAMICALLY
    # This ensures if the Cloudflare account ever changes, instructions update automatically
    hostbay_nameservers = await cloudflare_service.get_account_nameservers()
    
    # Build nameserver method instructions using dynamic nameservers
    nameserver_instructions = """1. Log in to your domain registrar (where you purchased the domain)
2. Navigate to DNS or Nameserver settings
3. Replace current nameservers with:
   - {ns1}
   - {ns2}
4. Save changes and wait 24-48 hours for propagation
5. Return to HostBay to verify the domain is linked""".format(
        ns1=hostbay_nameservers[0] if len(hostbay_nameservers) > 0 else "ns1.cloudflare.com",
        ns2=hostbay_nameservers[1] if len(hostbay_nameservers) > 1 else "ns2.cloudflare.com"
    )
    
    # Build A record method instructions
    a_record_instructions = """1. Log in to your domain registrar or DNS provider
2. Navigate to DNS record management
3. Add or update the following A records:
   - Type: A, Name: @ (root), Value: {server_ip}
   - Type: A, Name: www, Value: {server_ip}
4. Save changes and wait 1-4 hours for propagation
5. Return to HostBay to verify the domain is linked""".format(
        server_ip=server_ip
    )
    
    # Build important notes based on domain status
    important_notes = []
    
    if is_internal:
        important_notes.append("This domain was purchased through HostBay - DNS is already configured automatically.")
    
    if already_using_cloudflare:
        important_notes.append("Your domain is already using Cloudflare. Use the A Record method to avoid conflicts.")
        important_notes.append("If you switch nameservers, you may lose existing Cloudflare settings.")
    
    important_notes.extend([
        "Nameserver changes can take 24-48 hours to fully propagate worldwide.",
        "A Record changes typically propagate within 1-4 hours.",
        "Do not change both nameservers and A records - choose one method only."
    ])
    
    # Return structured response using DNSInstructionsResponse schema with proper model instances
    return DNSInstructionsResponse(
        domain=domain_name,
        domain_status=DomainStatus(
            is_internal=is_internal,
            already_using_cloudflare=already_using_cloudflare,
            current_nameservers=current_nameservers,
            recommendation=recommendation_text
        ),
        nameserver_method=NameserverMethod(
            nameservers=list(hostbay_nameservers),  # Dynamic from Cloudflare API
            instructions=nameserver_instructions,
            estimated_propagation="24-48 hours"
        ),
        a_record_method=ARecordMethod(
            server_ip=server_ip,
            instructions=a_record_instructions,
            records_to_add=[
                {"type": "A", "name": "@", "value": server_ip, "ttl": "3600"},
                {"type": "A", "name": "www", "value": server_ip, "ttl": "3600"}
            ],
            estimated_propagation="1-4 hours"
        ),
        important_notes=important_notes
    )
