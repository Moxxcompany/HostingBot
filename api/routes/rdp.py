"""
RDP Server Management Routes
"""
from decimal import Decimal
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Path
from api.middleware.authentication import get_api_key_from_header, check_permission
from pydantic import BaseModel, Field
from api.utils.responses import success_response
from api.utils.errors import ResourceNotFoundError, InternalServerError, BadRequestError
from services.vultr import vultr_service
from database import (
    execute_query, 
    execute_update,
    reserve_wallet_balance,
    get_user_wallet_balance_by_id,
    create_order_with_uuid
)
from admin_alerts import send_info_alert, send_error_alert
import asyncio

router = APIRouter()


class CreateRDPServerRequest(BaseModel):
    template_id: int = Field(..., description="RDP template ID (Windows version)")
    plan_id: int = Field(..., description="RDP plan ID")
    region: str = Field(..., description="Datacenter region ID (e.g., ewr, lhr, syd)")
    billing_cycle: str = Field("monthly", description="Billing cycle: monthly, quarterly, yearly")
    hostname: str = Field(None, description="Optional custom hostname")


@router.get("/rdp/plans", response_model=dict)
async def get_rdp_plans(
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get all available RDP plans with pricing"""
    check_permission(key_data, "rdp", "read")
    
    plans = await execute_query("""
        SELECT id, plan_name, vcpu_count, ram_mb, storage_gb, bandwidth_tb,
               vultr_monthly_price, our_monthly_price, is_active
        FROM rdp_plans
        WHERE is_active = true
        ORDER BY our_monthly_price ASC
    """)
    
    plans_list = []
    for plan in plans:
        plans_list.append({
            "id": plan['id'],
            "name": plan['plan_name'],
            "vcpu": plan['vcpu_count'],
            "ram_mb": plan['ram_mb'],
            "ram_gb": plan['ram_mb'] / 1024,
            "storage_gb": plan['storage_gb'],
            "bandwidth_tb": plan['bandwidth_tb'],
            "monthly_price": float(plan['our_monthly_price']),
            "quarterly_price": float(plan['our_monthly_price']) * 3 * 0.94,
            "yearly_price": float(plan['our_monthly_price']) * 12 * 0.89,
            "is_active": plan['is_active']
        })
    
    return success_response({"plans": plans_list})


@router.get("/rdp/templates", response_model=dict)
async def get_rdp_templates(
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get all available Windows templates"""
    check_permission(key_data, "rdp", "read")
    
    templates = await execute_query("""
        SELECT id, windows_version, edition, display_name, vultr_os_id, is_active
        FROM rdp_templates
        WHERE is_active = true
        ORDER BY windows_version DESC
    """)
    
    templates_list = []
    for template in templates:
        templates_list.append({
            "id": template['id'],
            "windows_version": template['windows_version'],
            "edition": template['edition'],
            "display_name": template['display_name'],
            "is_active": template['is_active']
        })
    
    return success_response({"templates": templates_list})


@router.get("/rdp/regions", response_model=dict)
async def get_rdp_regions(
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get all available datacenter regions"""
    check_permission(key_data, "rdp", "read")
    
    regions = vultr_service.get_regions()
    
    if not regions:
        raise InternalServerError("Failed to fetch datacenter regions")
    
    return success_response({"regions": regions})


@router.post("/rdp/servers", response_model=dict)
async def create_rdp_server(
    request: CreateRDPServerRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Create a new RDP server - OPTIMIZED with parallel DB queries"""
    check_permission(key_data, "rdp", "write")
    user_id = key_data["user_id"]
    
    # PERFORMANCE OPTIMIZATION: Fetch all required data in parallel
    import asyncio
    server_count_task = execute_query("""
        SELECT COUNT(*) as count FROM rdp_servers
        WHERE user_id = %s AND deleted_at IS NULL
    """, (user_id,))
    
    template_task = execute_query("""
        SELECT vultr_os_id, windows_version, edition
        FROM rdp_templates
        WHERE id = %s AND is_active = true
    """, (request.template_id,))
    
    plan_task = execute_query("""
        SELECT vultr_plan_id, plan_name, our_monthly_price
        FROM rdp_plans
        WHERE id = %s AND is_active = true
    """, (request.plan_id,))
    
    balance_task = get_user_wallet_balance_by_id(user_id)
    
    server_count, template, plan, current_balance = await asyncio.gather(
        server_count_task, template_task, plan_task, balance_task
    )
    
    if server_count and server_count[0]['count'] >= 10:
        raise BadRequestError("Maximum 10 RDP servers per user. Please delete an existing server first.")
    
    if not template or not plan:
        raise ResourceNotFoundError("Template or plan not found")
    
    template = template[0]
    plan = plan[0]
    monthly_price = float(plan['our_monthly_price'])
    
    # Calculate total based on billing cycle
    if request.billing_cycle == 'monthly':
        total_price = monthly_price
        period_months = 1
    elif request.billing_cycle == 'quarterly':
        total_price = monthly_price * 3 * 0.94
        period_months = 3
    elif request.billing_cycle == 'yearly':
        total_price = monthly_price * 12 * 0.89
        period_months = 12
    else:
        raise BadRequestError("Invalid billing cycle. Must be monthly, quarterly, or yearly")
    
    # Wallet balance already fetched above
    if current_balance < Decimal(str(total_price)):
        raise BadRequestError(
            f"Insufficient wallet balance. Required: ${total_price:.2f}, Available: ${float(current_balance):.2f}",
            {"required": total_price, "available": float(current_balance)}
        )
    
    # Reserve wallet balance
    hold_transaction_id = await reserve_wallet_balance(
        user_id,
        Decimal(str(total_price)),
        f"RDP server order hold"
    )
    
    if not hold_transaction_id:
        raise InternalServerError("Failed to reserve wallet balance")
    
    # Create order
    order_uuid = await create_order_with_uuid(
        user_id=user_id,
        order_type='rdp_server',
        total_amount=Decimal(str(total_price)),
        currency='USD',
        metadata={
            'template_id': request.template_id,
            'plan_id': request.plan_id,
            'region': request.region,
            'billing_cycle': request.billing_cycle,
            'period_months': period_months,
            'hostname': request.hostname
        }
    )
    
    # Get order ID
    order = await execute_query("""
        SELECT id FROM orders WHERE uuid_id = %s
    """, (order_uuid,))
    
    if not order:
        raise InternalServerError("Failed to create order")
    
    order_id = order[0]['id']
    
    # Mark order as completed (wallet already reserved)
    from database import debit_wallet_balance
    debit_success = await debit_wallet_balance(
        user_id,
        Decimal(str(total_price)),
        reference_type='rdp_server',
        reference_id=order_id,
        description=f"RDP Server purchase"
    )
    
    if not debit_success:
        raise InternalServerError("Payment processing failed")
    
    await execute_update("""
        UPDATE orders
        SET status = 'completed', completed_at = NOW()
        WHERE id = %s
    """, (order_id,))
    
    # Start provisioning asynchronously
    import time
    hostname = request.hostname or f"rdp-{user_id}-{int(time.time())}"
    label = f"HostBay RDP API - User {user_id}"
    
    # Create RDP instance
    instance = vultr_service.create_instance(
        region=request.region,
        plan=plan['vultr_plan_id'],
        os_id=template['vultr_os_id'],
        label=label,
        hostname=hostname
    )
    
    if not instance:
        raise InternalServerError("Failed to create RDP server instance")
    
    instance_id = instance.get('id')
    
    # Calculate next renewal
    next_renewal = datetime.now() + timedelta(days=period_months * 30)
    
    # Insert into rdp_servers
    await execute_update("""
        INSERT INTO rdp_servers (
            user_id, vultr_instance_id, template_id, plan_id, region, hostname,
            status, monthly_price, billing_cycle, next_renewal_date, auto_renew
        ) VALUES (%s, %s, %s, %s, %s, %s, 'provisioning', %s, %s, %s, true)
    """, (
        user_id, instance_id, request.template_id, request.plan_id, request.region,
        hostname, plan['our_monthly_price'], request.billing_cycle, next_renewal
    ))
    
    # Get server ID
    server = await execute_query("""
        SELECT id FROM rdp_servers WHERE vultr_instance_id = %s
    """, (instance_id,))
    
    if server:
        server_id = server[0]['id']
        
        # Link to rdp_orders
        await execute_update("""
            INSERT INTO rdp_orders (order_id, rdp_server_id, renewal_number)
            VALUES (%s, %s, 0)
        """, (order_id, server_id))
        
        # Wait for instance to be ready (async)
        asyncio.create_task(wait_for_rdp_instance_ready(instance_id, server_id, user_id, plan['plan_name'], request.region))
    
    # Send admin notification for provisioning start
    await send_info_alert(
        "RDP_API",
        f"✅ RDP server provisioning started via API: {plan['plan_name']} for user {user_id}",
        "hosting",
        {
            "user_id": user_id,
            "server_id": server_id if server else None,
            "instance_id": instance_id,
            "plan": plan['plan_name'],
            "region": request.region,
            "hostname": hostname
        }
    )
    
    return success_response({
        "message": "RDP server provisioning started",
        "server_id": server_id if server else None,
        "hostname": hostname,
        "status": "provisioning",
        "estimated_ready_time": "5-10 minutes"
    })


async def wait_for_rdp_instance_ready(instance_id: str, server_id: int, user_id: int, plan_name: str, region: str):
    """Background task to wait for instance to be ready and update credentials"""
    try:
        instance_ready = await vultr_service.wait_for_instance_ready(instance_id, timeout=600)
        
        if instance_ready:
            public_ip = instance_ready.get('main_ip', 'N/A')
            default_password = instance_ready.get('default_password', 'N/A')
            power_status = instance_ready.get('power_status', 'unknown')
            
            encrypted_password = vultr_service.encrypt_password(default_password) if default_password != 'N/A' else None
            
            await execute_update("""
                UPDATE rdp_servers
                SET public_ip = %s,
                    admin_password_encrypted = %s,
                    power_status = %s,
                    status = 'active',
                    activated_at = NOW()
                WHERE id = %s
            """, (public_ip, encrypted_password, power_status, server_id))
            
            # Send admin success notification
            await send_info_alert(
                "RDP_API",
                f"✅ RDP server provisioned successfully via API: {plan_name} for user {user_id}",
                "hosting",
                {
                    "user_id": user_id,
                    "server_id": server_id,
                    "instance_id": instance_id,
                    "plan": plan_name,
                    "region": region,
                    "public_ip": public_ip
                }
            )
        else:
            await execute_update("""
                UPDATE rdp_servers
                SET status = 'failed'
                WHERE id = %s
            """, (server_id,))
            
            # Send admin failure notification
            await send_error_alert(
                "RDP_API",
                f"❌ RDP server provisioning failed via API for user {user_id}",
                "hosting",
                {
                    "user_id": user_id,
                    "server_id": server_id,
                    "instance_id": instance_id,
                    "error": "Instance failed to become ready"
                }
            )
    except Exception as e:
        print(f"Error waiting for RDP instance: {e}")
        
        # Send admin error notification
        await send_error_alert(
            "RDP_API",
            f"❌ RDP server provisioning error via API for user {user_id}: {str(e)}",
            "hosting",
            {
                "user_id": user_id,
                "server_id": server_id,
                "instance_id": instance_id,
                "error": str(e)
            }
        )


@router.get("/rdp/servers", response_model=dict)
async def list_rdp_servers(
    key_data: dict = Depends(get_api_key_from_header)
):
    """List all RDP servers for the authenticated user"""
    check_permission(key_data, "rdp", "read")
    user_id = key_data["user_id"]
    
    servers = await execute_query("""
        SELECT rs.id, rs.vultr_instance_id, rs.hostname, rs.public_ip, rs.status,
               rs.power_status, rs.created_at, rs.activated_at, rs.next_renewal_date,
               rs.billing_cycle, rs.monthly_price, rs.auto_renew, rs.region,
               rp.plan_name, rp.vcpu_count, rp.ram_mb, rp.storage_gb,
               rt.windows_version, rt.edition
        FROM rdp_servers rs
        LEFT JOIN rdp_plans rp ON rs.plan_id = rp.id
        LEFT JOIN rdp_templates rt ON rs.template_id = rt.id
        WHERE rs.user_id = %s AND rs.deleted_at IS NULL
        ORDER BY rs.created_at DESC
    """, (user_id,))
    
    servers_list = []
    for server in servers:
        servers_list.append({
            "id": server['id'],
            "hostname": server['hostname'],
            "public_ip": server['public_ip'],
            "status": server['status'],
            "power_status": server['power_status'],
            "os": f"Windows Server {server['windows_version']} {server['edition']}",
            "plan": {
                "name": server['plan_name'],
                "vcpu": server['vcpu_count'],
                "ram_mb": server['ram_mb'],
                "storage_gb": server['storage_gb']
            },
            "region": server['region'],
            "billing": {
                "cycle": server['billing_cycle'],
                "monthly_price": float(server['monthly_price']),
                "next_renewal": server['next_renewal_date'].isoformat() if server['next_renewal_date'] else None,
                "auto_renew": server['auto_renew']
            },
            "created_at": server['created_at'].isoformat() if server['created_at'] else None,
            "activated_at": server['activated_at'].isoformat() if server['activated_at'] else None
        })
    
    return success_response({"servers": servers_list, "total": len(servers_list)})


@router.get("/rdp/servers/{server_id}", response_model=dict)
async def get_rdp_server_details(
    server_id: int = Path(..., description="RDP server ID"),
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get detailed information about a specific RDP server"""
    check_permission(key_data, "rdp", "read")
    user_id = key_data["user_id"]
    
    server = await execute_query("""
        SELECT rs.*, rp.plan_name, rp.vcpu_count, rp.ram_mb, rp.storage_gb,
               rt.windows_version, rt.edition
        FROM rdp_servers rs
        LEFT JOIN rdp_plans rp ON rs.plan_id = rp.id
        LEFT JOIN rdp_templates rt ON rs.template_id = rt.id
        WHERE rs.id = %s AND rs.user_id = %s AND rs.deleted_at IS NULL
    """, (server_id, user_id))
    
    if not server:
        raise ResourceNotFoundError("RDP server not found")
    
    server = server[0]
    
    # Decrypt password
    password = None
    if server['admin_password_encrypted']:
        password = vultr_service.decrypt_password(server['admin_password_encrypted'])
    
    return success_response({
        "id": server['id'],
        "hostname": server['hostname'],
        "public_ip": server['public_ip'],
        "status": server['status'],
        "power_status": server['power_status'],
        "os": f"Windows Server {server['windows_version']} {server['edition']}",
        "credentials": {
            "username": "Administrator",
            "password": password if server['status'] == 'active' else None
        },
        "plan": {
            "name": server['plan_name'],
            "vcpu": server['vcpu_count'],
            "ram_mb": server['ram_mb'],
            "storage_gb": server['storage_gb']
        },
        "region": server['region'],
        "billing": {
            "cycle": server['billing_cycle'],
            "monthly_price": float(server['monthly_price']),
            "next_renewal": server['next_renewal_date'].isoformat() if server['next_renewal_date'] else None,
            "auto_renew": server['auto_renew']
        },
        "created_at": server['created_at'].isoformat() if server['created_at'] else None,
        "activated_at": server['activated_at'].isoformat() if server['activated_at'] else None
    })


@router.delete("/rdp/servers/{server_id}", response_model=dict)
async def delete_rdp_server(
    server_id: int = Path(..., description="RDP server ID"),
    key_data: dict = Depends(get_api_key_from_header)
):
    """Delete an RDP server"""
    check_permission(key_data, "rdp", "write")
    user_id = key_data["user_id"]
    
    server = await execute_query("""
        SELECT vultr_instance_id, hostname FROM rdp_servers
        WHERE id = %s AND user_id = %s AND deleted_at IS NULL
    """, (server_id, user_id))
    
    if not server:
        raise ResourceNotFoundError("RDP server not found")
    
    instance_id = server[0]['vultr_instance_id']
    hostname = server[0]['hostname']
    
    # Delete RDP server
    success = vultr_service.delete_instance(instance_id)
    
    if not success:
        raise InternalServerError("Failed to delete RDP server")
    
    # Mark as deleted
    await execute_update("""
        UPDATE rdp_servers
        SET deleted_at = NOW(), status = 'deleted', auto_renew = false
        WHERE id = %s
    """, (server_id,))
    
    return success_response({
        "message": f"Server {hostname} deleted successfully",
        "server_id": server_id
    })


@router.post("/rdp/servers/{server_id}/start", response_model=dict)
async def start_rdp_server(
    server_id: int = Path(..., description="RDP server ID"),
    key_data: dict = Depends(get_api_key_from_header)
):
    """Start an RDP server"""
    check_permission(key_data, "rdp", "write")
    user_id = key_data["user_id"]
    
    server = await execute_query("""
        SELECT vultr_instance_id FROM rdp_servers
        WHERE id = %s AND user_id = %s AND deleted_at IS NULL
    """, (server_id, user_id))
    
    if not server:
        raise ResourceNotFoundError("RDP server not found")
    
    instance_id = server[0]['vultr_instance_id']
    
    success = vultr_service.start_instance(instance_id)
    
    if not success:
        raise InternalServerError("Failed to start server")
    
    await execute_update("""
        UPDATE rdp_servers SET power_status = 'running' WHERE id = %s
    """, (server_id,))
    
    return success_response({"message": "Server is starting", "server_id": server_id})


@router.post("/rdp/servers/{server_id}/stop", response_model=dict)
async def stop_rdp_server(
    server_id: int = Path(..., description="RDP server ID"),
    key_data: dict = Depends(get_api_key_from_header)
):
    """Stop an RDP server"""
    check_permission(key_data, "rdp", "write")
    user_id = key_data["user_id"]
    
    server = await execute_query("""
        SELECT vultr_instance_id FROM rdp_servers
        WHERE id = %s AND user_id = %s AND deleted_at IS NULL
    """, (server_id, user_id))
    
    if not server:
        raise ResourceNotFoundError("RDP server not found")
    
    instance_id = server[0]['vultr_instance_id']
    
    success = vultr_service.stop_instance(instance_id)
    
    if not success:
        raise InternalServerError("Failed to stop server")
    
    await execute_update("""
        UPDATE rdp_servers SET power_status = 'stopped' WHERE id = %s
    """, (server_id,))
    
    return success_response({"message": "Server is stopping", "server_id": server_id})


@router.post("/rdp/servers/{server_id}/restart", response_model=dict)
async def restart_rdp_server(
    server_id: int = Path(..., description="RDP server ID"),
    key_data: dict = Depends(get_api_key_from_header)
):
    """Restart an RDP server"""
    check_permission(key_data, "rdp", "write")
    user_id = key_data["user_id"]
    
    server = await execute_query("""
        SELECT vultr_instance_id FROM rdp_servers
        WHERE id = %s AND user_id = %s AND deleted_at IS NULL
    """, (server_id, user_id))
    
    if not server:
        raise ResourceNotFoundError("RDP server not found")
    
    instance_id = server[0]['vultr_instance_id']
    
    success = vultr_service.reboot_instance(instance_id)
    
    if not success:
        raise InternalServerError("Failed to restart server")
    
    return success_response({"message": "Server is restarting", "server_id": server_id})


@router.post("/rdp/servers/{server_id}/reinstall", response_model=dict)
async def reinstall_rdp_server(
    server_id: int = Path(..., description="RDP server ID"),
    key_data: dict = Depends(get_api_key_from_header)
):
    """Reinstall OS on an RDP server (resets password)"""
    check_permission(key_data, "rdp", "write")
    user_id = key_data["user_id"]
    
    server = await execute_query("""
        SELECT vultr_instance_id FROM rdp_servers
        WHERE id = %s AND user_id = %s AND deleted_at IS NULL
    """, (server_id, user_id))
    
    if not server:
        raise ResourceNotFoundError("RDP server not found")
    
    instance_id = server[0]['vultr_instance_id']
    
    success = vultr_service.reinstall_instance(instance_id)
    
    if not success:
        raise InternalServerError("Failed to reinstall server")
    
    # Update status to provisioning
    await execute_update("""
        UPDATE rdp_servers
        SET status = 'provisioning', admin_password_encrypted = NULL, power_status = 'reinstalling'
        WHERE id = %s
    """, (server_id,))
    
    # Wait for reinstall to complete (async)
    asyncio.create_task(wait_for_rdp_reinstall_complete(instance_id, server_id))
    
    return success_response({
        "message": "OS reinstall started. New credentials will be available once complete.",
        "server_id": server_id,
        "estimated_time": "10-15 minutes"
    })


async def wait_for_rdp_reinstall_complete(instance_id: str, server_id: int):
    """Background task to wait for OS reinstall to complete"""
    try:
        instance_ready = await vultr_service.wait_for_instance_ready(instance_id, timeout=900)
        
        if instance_ready:
            new_password = instance_ready.get('default_password', 'N/A')
            encrypted_password = vultr_service.encrypt_password(new_password) if new_password != 'N/A' else None
            
            await execute_update("""
                UPDATE rdp_servers
                SET admin_password_encrypted = %s,
                    power_status = %s,
                    status = 'active'
                WHERE id = %s
            """, (encrypted_password, instance_ready.get('power_status', 'running'), server_id))
    except Exception as e:
        print(f"Error waiting for reinstall: {e}")
