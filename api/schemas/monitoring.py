"""
Monitoring schemas.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class DomainHistoryResponse(BaseModel):
    """Domain history event"""
    timestamp: str
    event_type: str
    description: str
    details: Dict[str, Any]


class PropagationStatusResponse(BaseModel):
    """DNS propagation status"""
    domain: str
    record_type: str
    propagated: bool
    servers_checked: int
    servers_propagated: int
    locations: List[Dict[str, Any]]


class SSLExpiryResponse(BaseModel):
    """SSL certificate expiry information"""
    domain: str
    has_ssl: bool
    issuer: Optional[str]
    expires_at: Optional[str]
    days_remaining: Optional[int]
    is_valid: bool


class UptimeResponse(BaseModel):
    """Hosting uptime statistics"""
    subscription_id: int
    uptime_percentage: float
    total_checks: int
    successful_checks: int
    failed_checks: int
    last_check: str


class SystemStatusResponse(BaseModel):
    """System status"""
    status: str
    services: Dict[str, Any]
    last_updated: str
