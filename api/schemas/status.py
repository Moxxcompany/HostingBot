"""
Status tracking and bulk operation schemas.
"""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class HostingProvisionIntentResponse(BaseModel):
    """Hosting provision intent status response"""
    intent_id: int
    status: str = Field(..., description="pending, processing, completed, failed, settlement_failed")
    domain_name: Optional[str]
    service_type: str = Field(..., description="hosting_standalone, hosting_with_existing_domain, hosting_domain_bundle")
    quote_price: Optional[float]
    currency: str = "USD"
    error_message: Optional[str]
    processing_started_at: Optional[str]
    completed_at: Optional[str]
    created_at: str
    updated_at: str


class BulkDomainStatusRequest(BaseModel):
    """Request to check status of multiple domains"""
    domains: List[str] = Field(..., min_length=1, max_length=100, examples=[["example.com", "example.org"]])


class DomainStatusInfo(BaseModel):
    """Domain status information"""
    domain: str
    status: str
    dns_active: bool
    ssl_active: bool
    dns_zone_id: Optional[str] = Field(None, description="DNS zone identifier")


class BulkDomainStatusResponse(BaseModel):
    """Response for bulk domain status check"""
    results: List[DomainStatusInfo]
    total: int
    found: int
    not_found: int


class BulkHostingStatusRequest(BaseModel):
    """Request to check status of multiple hosting subscriptions"""
    subscription_ids: List[int] = Field(..., min_length=1, max_length=100)


class HostingStatusInfo(BaseModel):
    """Hosting subscription status information"""
    id: int
    domain_name: str
    plan: str
    status: str
    is_active: bool
    expires_at: Optional[str]


class BulkHostingStatusResponse(BaseModel):
    """Response for bulk hosting status check"""
    results: List[HostingStatusInfo]
    total: int
    found: int
    not_found: int


class DomainTransferStatusResponse(BaseModel):
    """Domain transfer status response"""
    domain_name: str
    status: str = Field(..., description="pending, awaiting_approval, approved, completed, rejected, failed")
    initiated_at: Optional[str]
    can_expedite: bool = False
    days_remaining: Optional[int]
    transfer_details: Optional[Dict]


class BulkOperationInfo(BaseModel):
    """Information about a single item in bulk operation"""
    item_id: str
    status: str
    success: bool
    error: Optional[str]
    created_at: Optional[str]


class BulkOperationResponse(BaseModel):
    """Bulk operation tracking response"""
    operation_id: str
    operation_type: str = Field(..., description="bulk_domain_registration, bulk_dns_update, etc.")
    status: str = Field(..., description="pending, processing, completed, partial_success, failed")
    total_items: int
    completed: int
    failed: int
    pending: int
    created_at: str
    updated_at: str
    results: Optional[List[BulkOperationInfo]]


class DomainRegistrationAttempt(BaseModel):
    """Single domain registration attempt record"""
    attempt_id: int
    timestamp: str
    status: str = Field(..., description="success, failed, pending")
    error_message: Optional[str]
    registry_response: Optional[Dict] = Field(None, description="Domain registry response details")
    amount_charged: Optional[float]


class DomainRegistrationHistoryResponse(BaseModel):
    """Domain registration history response"""
    domain_name: str
    attempts: List[DomainRegistrationAttempt]
    total_attempts: int
    last_attempt_at: Optional[str]
