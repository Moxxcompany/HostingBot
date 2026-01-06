"""
Webhook Management Routes
"""
import secrets
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, Path, Query
from api.middleware.authentication import get_api_key_from_header, check_permission
from api.schemas.webhook import (
    WebhookCreate,
    WebhookUpdate,
    WebhookResponse,
    WebhookEventList
)
from api.utils.responses import success_response
from api.utils.errors import ResourceNotFoundError, InternalServerError, BadRequestError
from database import execute_query, execute_update

router = APIRouter()


@router.post("/webhooks", response_model=dict)
async def create_webhook(
    request: WebhookCreate,
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Create a new webhook for receiving event notifications.
    
    The secret will be shown only once in this response.
    Use it to verify webhook signatures (HMAC-SHA256).
    """
    check_permission(key_data, "webhooks", "write")
    user_id = key_data["user_id"]
    
    # Generate HMAC secret for signature verification
    webhook_secret = secrets.token_hex(32)
    
    # Convert events list to JSONB
    events_json = json.dumps(request.events)
    
    # Insert webhook into database
    try:
        result = await execute_query("""
            INSERT INTO webhooks (user_id, url, secret, events, description, is_active, created_at)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s, CURRENT_TIMESTAMP)
            RETURNING id, user_id, url, events, description, is_active, created_at, 
                      last_triggered_at, success_count, failure_count
        """, (user_id, str(request.url), webhook_secret, events_json, request.description, request.is_active))
        
        if not result:
            raise InternalServerError("Failed to create webhook")
        
        webhook = result[0]
        
        return success_response({
            "id": webhook["id"],
            "url": webhook["url"],
            "events": webhook["events"],
            "description": webhook["description"],
            "is_active": webhook["is_active"],
            "secret": webhook_secret,
            "created_at": webhook["created_at"].isoformat() if webhook["created_at"] else None,
            "last_triggered_at": webhook["last_triggered_at"].isoformat() if webhook["last_triggered_at"] else None,
            "success_count": webhook["success_count"] or 0,
            "failure_count": webhook["failure_count"] or 0
        }, "Webhook created successfully. Save the secret - it won't be shown again!")
        
    except Exception as e:
        raise InternalServerError(f"Failed to create webhook: {str(e)}")


@router.get("/webhooks", response_model=dict)
async def list_webhooks(
    key_data: dict = Depends(get_api_key_from_header),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page")
):
    """
    List all webhooks for the authenticated user.
    
    The secret is not included in the response for security.
    """
    check_permission(key_data, "webhooks", "read")
    user_id = key_data["user_id"]
    
    # Calculate offset
    offset = (page - 1) * per_page
    
    # Get total count
    count_result = await execute_query("""
        SELECT COUNT(*) as total FROM webhooks WHERE user_id = %s
    """, (user_id,))
    total = count_result[0]["total"] if count_result else 0
    
    # Get webhooks
    webhooks = await execute_query("""
        SELECT id, user_id, url, events, description, is_active, created_at,
               last_triggered_at, success_count, failure_count
        FROM webhooks
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """, (user_id, per_page, offset))
    
    # Format response
    webhook_list = []
    for webhook in webhooks:
        webhook_list.append({
            "id": webhook["id"],
            "url": webhook["url"],
            "events": webhook["events"],
            "description": webhook["description"],
            "is_active": webhook["is_active"],
            "secret": None,
            "created_at": webhook["created_at"].isoformat() if webhook["created_at"] else None,
            "last_triggered_at": webhook["last_triggered_at"].isoformat() if webhook["last_triggered_at"] else None,
            "success_count": webhook["success_count"] or 0,
            "failure_count": webhook["failure_count"] or 0
        })
    
    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page
    
    return {
        "success": True,
        "data": webhook_list,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    }


@router.get("/webhooks/{webhook_id}", response_model=dict)
async def get_webhook(
    webhook_id: int = Path(..., description="Webhook ID"),
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Get details of a specific webhook.
    
    The secret is not included in the response for security.
    """
    check_permission(key_data, "webhooks", "read")
    user_id = key_data["user_id"]
    
    # Get webhook
    result = await execute_query("""
        SELECT id, user_id, url, events, description, is_active, created_at,
               last_triggered_at, success_count, failure_count
        FROM webhooks
        WHERE id = %s AND user_id = %s
    """, (webhook_id, user_id))
    
    if not result:
        raise ResourceNotFoundError("webhook", str(webhook_id))
    
    webhook = result[0]
    
    return success_response({
        "id": webhook["id"],
        "url": webhook["url"],
        "events": webhook["events"],
        "description": webhook["description"],
        "is_active": webhook["is_active"],
        "secret": None,
        "created_at": webhook["created_at"].isoformat() if webhook["created_at"] else None,
        "last_triggered_at": webhook["last_triggered_at"].isoformat() if webhook["last_triggered_at"] else None,
        "success_count": webhook["success_count"] or 0,
        "failure_count": webhook["failure_count"] or 0
    })


@router.patch("/webhooks/{webhook_id}", response_model=dict)
async def update_webhook(
    request: WebhookUpdate,
    webhook_id: int = Path(..., description="Webhook ID"),
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Update a webhook configuration.
    
    Only the fields provided in the request will be updated.
    """
    check_permission(key_data, "webhooks", "write")
    user_id = key_data["user_id"]
    
    # Verify webhook exists and belongs to user
    check_result = await execute_query("""
        SELECT id FROM webhooks WHERE id = %s AND user_id = %s
    """, (webhook_id, user_id))
    
    if not check_result:
        raise ResourceNotFoundError("webhook", str(webhook_id))
    
    # Build update query dynamically based on provided fields
    update_fields = []
    values = []
    
    if request.url is not None:
        update_fields.append("url = %s")
        values.append(str(request.url))
    
    if request.events is not None:
        update_fields.append("events = %s::jsonb")
        values.append(json.dumps(request.events))
    
    if request.description is not None:
        update_fields.append("description = %s")
        values.append(request.description)
    
    if request.is_active is not None:
        update_fields.append("is_active = %s")
        values.append(request.is_active)
    
    if not update_fields:
        raise BadRequestError("No fields to update")
    
    # Add webhook_id and user_id to values for WHERE clause
    values.extend([webhook_id, user_id])
    
    # Execute update
    await execute_update(f"""
        UPDATE webhooks
        SET {', '.join(update_fields)}
        WHERE id = %s AND user_id = %s
    """, tuple(values))
    
    # Return updated webhook
    result = await execute_query("""
        SELECT id, user_id, url, events, description, is_active, created_at,
               last_triggered_at, success_count, failure_count
        FROM webhooks
        WHERE id = %s AND user_id = %s
    """, (webhook_id, user_id))
    
    webhook = result[0]
    
    return success_response({
        "id": webhook["id"],
        "url": webhook["url"],
        "events": webhook["events"],
        "description": webhook["description"],
        "is_active": webhook["is_active"],
        "secret": None,
        "created_at": webhook["created_at"].isoformat() if webhook["created_at"] else None,
        "last_triggered_at": webhook["last_triggered_at"].isoformat() if webhook["last_triggered_at"] else None,
        "success_count": webhook["success_count"] or 0,
        "failure_count": webhook["failure_count"] or 0
    }, "Webhook updated successfully")


@router.delete("/webhooks/{webhook_id}", response_model=dict)
async def delete_webhook(
    webhook_id: int = Path(..., description="Webhook ID"),
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    Delete a webhook.
    
    All associated delivery records will also be deleted (CASCADE).
    """
    check_permission(key_data, "webhooks", "write")
    user_id = key_data["user_id"]
    
    # Delete webhook (will cascade to webhook_deliveries)
    result = await execute_update("""
        DELETE FROM webhooks
        WHERE id = %s AND user_id = %s
    """, (webhook_id, user_id))
    
    # Check if webhook existed
    check_result = await execute_query("""
        SELECT EXISTS(SELECT 1 FROM webhooks WHERE id = %s)
    """, (webhook_id,))
    
    webhook_exists = check_result[0]["exists"] if check_result else False
    
    if webhook_exists:
        raise ResourceNotFoundError("webhook", str(webhook_id))
    
    return success_response(
        {"webhook_id": webhook_id},
        "Webhook deleted successfully"
    )


@router.get("/webhooks/events", response_model=dict)
async def list_webhook_events(
    key_data: dict = Depends(get_api_key_from_header)
):
    """
    List all available webhook event types.
    
    Use these event types when creating or updating webhooks.
    """
    check_permission(key_data, "webhooks", "read")
    
    # Get all event types from database
    events = await execute_query("""
        SELECT event_type, description, category
        FROM webhook_events
        ORDER BY category, event_type
    """)
    
    # Format response
    event_list = []
    for event in events:
        event_list.append({
            "event_type": event["event_type"],
            "description": event["description"],
            "category": event["category"]
        })
    
    return success_response({
        "events": event_list,
        "total": len(event_list)
    })
