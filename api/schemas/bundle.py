"""
Hosting bundle schemas.
"""
from typing import Dict, Optional
from pydantic import BaseModel, Field
from api.schemas.domain import ContactInfo


class CreateDomainHostingBundleRequest(BaseModel):
    """Request to create new domain + hosting bundle"""
    domain_name: str = Field(..., pattern=r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,}$')
    plan: str = Field(..., pattern="^(pro_7day|pro_30day)$")
    period: int = Field(1, ge=1, le=10)
    contacts: Dict[str, ContactInfo]
    auto_renew: bool = True


class BundleResponse(BaseModel):
    """Bundle information response"""
    id: int
    type: str
    domain_name: str
    status: str
    order_id: str
    created_at: str
    completed_at: Optional[str]
