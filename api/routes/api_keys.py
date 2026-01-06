"""
API Key Management Routes
"""
from fastapi import APIRouter, Depends
from api.middleware.authentication import get_api_key_from_header
from api.services.api_key_service import APIKeyService
from api.services.rate_limit_service import RateLimitService
from api.schemas.api_key import (
    CreateAPIKeyRequest,
    UpdateAPIKeyRequest,
    APIKeyCreatedResponse,
    APIKeyResponse,
    UsageStatsResponse
)
from api.utils.responses import success_response
from api.utils.errors import ResourceNotFoundError

router = APIRouter()


@router.post("/keys", response_model=dict)
async def create_api_key(
    request: CreateAPIKeyRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Create a new API key"""
    user_id = key_data["user_id"]
    
    result = await APIKeyService.create_api_key(
        user_id=user_id,
        name=request.name,
        permissions=request.permissions.dict() if request.permissions else None,
        rate_limit_per_hour=request.rate_limit_per_hour,
        rate_limit_per_day=request.rate_limit_per_day,
        expires_in_days=request.expires_in_days,
        ip_whitelist=request.ip_whitelist
    )
    
    return success_response(result, "API key created successfully. Store it securely - it won't be shown again!")


@router.get("/keys", response_model=dict)
async def list_api_keys(
    include_revoked: bool = False,
    key_data: dict = Depends(get_api_key_from_header)
):
    """List all API keys for the authenticated user"""
    user_id = key_data["user_id"]
    
    keys = await APIKeyService.list_api_keys(user_id, include_revoked)
    
    return success_response({"keys": keys, "total": len(keys)})


@router.get("/keys/{key_id}", response_model=dict)
async def get_api_key(
    key_id: int,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get specific API key details"""
    user_id = key_data["user_id"]
    
    keys = await APIKeyService.list_api_keys(user_id, include_revoked=True)
    key = next((k for k in keys if k["id"] == key_id), None)
    
    if not key:
        raise ResourceNotFoundError("API key", str(key_id))
    
    return success_response(key)


@router.patch("/keys/{key_id}", response_model=dict)
async def update_api_key(
    key_id: int,
    request: UpdateAPIKeyRequest,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Update API key settings"""
    user_id = key_data["user_id"]
    
    success = await APIKeyService.update_api_key(
        key_id=key_id,
        user_id=user_id,
        name=request.name,
        permissions=request.permissions.dict() if request.permissions else None,
        rate_limit_per_hour=request.rate_limit_per_hour,
        rate_limit_per_day=request.rate_limit_per_day
    )
    
    if not success:
        raise ResourceNotFoundError("API key", str(key_id))
    
    return success_response({"updated": True}, "API key updated successfully")


@router.delete("/keys/{key_id}", response_model=dict)
async def revoke_api_key(
    key_id: int,
    reason: str = "User requested",
    key_data: dict = Depends(get_api_key_from_header)
):
    """Revoke an API key"""
    user_id = key_data["user_id"]
    
    success = await APIKeyService.revoke_api_key(key_id, user_id, reason)
    
    if not success:
        raise ResourceNotFoundError("API key", str(key_id))
    
    return success_response({"revoked": True}, "API key revoked successfully")


@router.get("/keys/{key_id}/usage", response_model=dict)
async def get_api_key_usage(
    key_id: int,
    hours: int = 24,
    key_data: dict = Depends(get_api_key_from_header)
):
    """Get usage statistics for an API key"""
    user_id = key_data["user_id"]
    
    keys = await APIKeyService.list_api_keys(user_id, include_revoked=True)
    key = next((k for k in keys if k["id"] == key_id), None)
    
    if not key:
        raise ResourceNotFoundError("API key", str(key_id))
    
    stats = await RateLimitService.get_usage_stats(key_id, hours)
    
    return success_response(stats)
