"""
API Key schemas.
"""
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class PermissionsSchema(BaseModel):
    """API key permissions"""
    domains: Dict[str, bool] = Field(default={"read": True, "write": True})
    dns: Dict[str, bool] = Field(default={"read": True, "write": True})
    nameservers: Dict[str, bool] = Field(default={"read": True, "write": True})
    hosting: Dict[str, bool] = Field(default={"read": True, "write": True})
    wallet: Dict[str, bool] = Field(default={"read": True, "write": False})
    orders: Dict[str, bool] = Field(default={"read": True, "write": False})


class CreateAPIKeyRequest(BaseModel):
    """Request to create new API key"""
    name: str = Field(..., min_length=1, max_length=100, description="Key name/description")
    permissions: Optional[PermissionsSchema] = None
    rate_limit_per_hour: int = Field(1000, ge=1, le=10000)
    rate_limit_per_day: int = Field(10000, ge=1, le=100000)
    expires_in_days: Optional[int] = Field(None, ge=1, le=3650, description="Days until expiration")
    ip_whitelist: Optional[List[str]] = Field(None, description="Allowed IP addresses/CIDR ranges")


class UpdateAPIKeyRequest(BaseModel):
    """Request to update API key"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    permissions: Optional[PermissionsSchema] = None
    rate_limit_per_hour: Optional[int] = Field(None, ge=1, le=10000)
    rate_limit_per_day: Optional[int] = Field(None, ge=1, le=100000)


class APIKeyResponse(BaseModel):
    """API key response (without full key)"""
    id: int
    key_prefix: str
    name: Optional[str]
    permissions: Dict
    rate_limit_per_hour: int
    rate_limit_per_day: int
    created_at: str
    last_used_at: Optional[str]
    expires_at: Optional[str]
    is_active: bool


class APIKeyCreatedResponse(APIKeyResponse):
    """API key created response (includes full key once)"""
    key: str = Field(..., description="Full API key - shown only once!")


class UsageStatsResponse(BaseModel):
    """API key usage statistics"""
    period_hours: int
    total_requests: int
    avg_response_time_ms: float
    status_breakdown: Dict[str, int]
    top_endpoints: List[Dict]
