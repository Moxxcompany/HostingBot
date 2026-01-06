"""
Domain linking schemas.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StartDomainLinkingRequest(BaseModel):
    """Request to start domain linking"""
    linking_mode: str = Field(..., pattern="^(smart|manual)$", description="Linking mode: smart or manual")
    hosting_plan: Optional[str] = Field(None, pattern="^(pro_7day|pro_30day)$")


class DomainLinkingStatusResponse(BaseModel):
    """Domain linking status"""
    domain: str
    status: str
    progress: int
    current_step: str
    linking_mode: str
    updated_at: str
    estimated_completion: Optional[str]


class DomainLinkingInstructionsResponse(BaseModel):
    """Domain linking instructions"""
    mode: str
    instructions: str
    nameservers: Optional[List[str]] = None
    dns_records: Optional[List[Dict[str, Any]]] = None
    verification_token: Optional[str] = None
    estimated_time: str


class LinkingModesResponse(BaseModel):
    """Available linking modes"""
    modes: List[Dict[str, Any]]


# ====================================================================
# NEW: DNS Instructions Response Models for External Domain Linking
# ====================================================================

class NameserverMethod(BaseModel):
    """Nameserver method details for domain linking"""
    nameservers: List[str] = Field(
        ..., 
        description="Cloudflare nameservers to set at your domain registrar"
    )
    instructions: str = Field(
        ...,
        description="Step-by-step instructions for updating nameservers"
    )
    estimated_propagation: str = Field(
        default="24-48 hours",
        description="Estimated time for DNS changes to propagate globally"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "nameservers": ["anderson.ns.cloudflare.com", "leanna.ns.cloudflare.com"],
                "instructions": "1. Log in to your domain registrar\n2. Find DNS/Nameserver settings\n3. Update nameservers to the values above",
                "estimated_propagation": "24-48 hours"
            }
        }


class ARecordMethod(BaseModel):
    """A Record method details for domain linking"""
    server_ip: str = Field(
        ...,
        description="cPanel server IP address to point your domain to"
    )
    instructions: str = Field(
        ...,
        description="Step-by-step instructions for adding A record"
    )
    records_to_add: List[Dict[str, str]] = Field(
        ...,
        description="DNS records to add at your registrar"
    )
    estimated_propagation: str = Field(
        default="1-4 hours",
        description="Estimated time for DNS changes to propagate"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "server_ip": "123.45.67.89",
                "instructions": "1. Log in to your domain registrar\n2. Find DNS record settings\n3. Add A records as shown above",
                "records_to_add": [
                    {"type": "A", "name": "@", "value": "123.45.67.89"},
                    {"type": "A", "name": "www", "value": "123.45.67.89"}
                ],
                "estimated_propagation": "1-4 hours"
            }
        }


class DomainStatus(BaseModel):
    """Current domain status for edge case handling"""
    is_internal: bool = Field(
        ...,
        description="True if domain was purchased through HostBay platform"
    )
    already_using_cloudflare: bool = Field(
        ...,
        description="True if domain nameservers already point to Cloudflare"
    )
    current_nameservers: List[str] = Field(
        default=[],
        description="Current nameservers configured for the domain"
    )
    recommendation: str = Field(
        ...,
        description="Recommended linking method based on current domain status"
    )


class DNSInstructionsResponse(BaseModel):
    """
    Complete DNS instructions for external domain linking.
    Provides both nameserver and A record methods with edge case handling.
    """
    domain: str = Field(..., description="Domain name being linked")
    domain_status: DomainStatus = Field(
        ...,
        description="Current domain status and edge case detection"
    )
    nameserver_method: NameserverMethod = Field(
        ...,
        description="Instructions for nameserver-based linking (recommended)"
    )
    a_record_method: ARecordMethod = Field(
        ...,
        description="Instructions for A record-based linking (alternative)"
    )
    important_notes: List[str] = Field(
        default=[],
        description="Important notes and warnings for the user"
    )
