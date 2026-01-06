"""
Webhook management schemas.
"""
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


class WebhookCreate(BaseModel):
    """Request to create a webhook"""
    url: HttpUrl = Field(..., description="HTTPS URL to receive webhook notifications", examples=["https://customer.com/webhook"])
    events: List[str] = Field(..., min_length=1, description="Event types to subscribe to", examples=[["domain.registered", "hosting.provisioned", "payment.confirmed"]])
    description: Optional[str] = Field(None, max_length=500, description="Optional description for this webhook")
    is_active: bool = Field(True, description="Whether webhook is active")


class WebhookUpdate(BaseModel):
    """Request to update a webhook"""
    url: Optional[HttpUrl] = None
    events: Optional[List[str]] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class WebhookResponse(BaseModel):
    """Webhook information response"""
    id: int
    url: str
    events: List[str]
    description: Optional[str]
    is_active: bool
    secret: Optional[str] = Field(None, description="HMAC secret for verifying webhook signatures (shown only once)")
    created_at: str
    last_triggered_at: Optional[str]
    success_count: int = 0
    failure_count: int = 0


class WebhookDelivery(BaseModel):
    """Webhook delivery attempt information"""
    id: int
    webhook_id: int
    event_type: str
    payload: dict
    response_code: Optional[int]
    response_body: Optional[str]
    status: str = Field(..., description="pending, success, failed, retrying")
    attempts: int
    created_at: str
    delivered_at: Optional[str]


class WebhookEventList(BaseModel):
    """List of available webhook events"""
    events: List[str] = [
        "domain.registered",
        "domain.renewed",
        "domain.transferred",
        "domain.deleted",
        "domain.dns_updated",
        "hosting.provisioned",
        "hosting.renewed",
        "hosting.suspended",
        "hosting.unsuspended",
        "hosting.deleted",
        "payment.confirmed",
        "payment.failed",
        "wallet.topup",
        "order.completed",
        "order.failed"
    ]
