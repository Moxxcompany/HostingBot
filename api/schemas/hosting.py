"""
Hosting management schemas.
"""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class HostingPlanResponse(BaseModel):
    """Hosting plan information"""
    id: int
    name: str
    plan_code: str
    price: float
    duration_days: int
    daily_price: float
    storage_gb: int
    bandwidth_gb: int
    databases: int
    email_accounts: int
    subdomains: str
    features: List[str]


class UnifiedOrderHostingRequest(BaseModel):
    """
    Unified request to order hosting for any domain type.
    
    domain_type options:
    - "new": Register a new domain + create hosting (domain_name optional, auto-generated if not provided)
    - "existing": Use a domain already registered in your HostBay account (domain_name required)
    - "external": Use a domain registered at another registrar (domain_name required, linking_mode optional)
    """
    domain_name: Optional[str] = Field(None, description="Domain name (required for existing/external, optional for new)")
    domain_type: str = Field(..., pattern="^(new|existing|external)$", description="Type of domain: new, existing, or external")
    plan: str = Field(..., pattern="^(pro_7day|pro_30day)$", examples=["pro_30day"])
    period: int = Field(1, ge=1, le=12, description="Billing periods", examples=[1])
    linking_mode: Optional[str] = Field("nameserver", pattern="^(nameserver|a_record)$", description="For external domains: nameserver or a_record method")
    auto_renew: bool = Field(True, description="Enable automatic renewal before expiration")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "domain_name": "example.com",
                    "domain_type": "new",
                    "plan": "pro_30day",
                    "period": 1,
                    "auto_renew": True
                },
                {
                    "domain_name": "myexisting.com",
                    "domain_type": "existing",
                    "plan": "pro_30day",
                    "period": 1,
                    "auto_renew": True
                },
                {
                    "domain_name": "external-domain.com",
                    "domain_type": "external",
                    "plan": "pro_30day",
                    "period": 1,
                    "linking_mode": "nameserver",
                    "auto_renew": True
                }
            ]
        }
    }


class OrderHostingRequest(BaseModel):
    """Request to order hosting (DEPRECATED - use UnifiedOrderHostingRequest)"""
    plan: str = Field(..., pattern="^(pro_7day|pro_30day)$", examples=["pro_30day"])
    period: int = Field(1, ge=1, le=12, description="Billing periods", examples=[1])
    domain_name: Optional[str] = Field(None, examples=["example.com"])
    auto_renew: bool = Field(True, description="Enable automatic renewal before expiration")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "plan": "pro_30day",
                    "period": 1,
                    "domain_name": "example.com",
                    "auto_renew": True
                }
            ]
        }
    }


class OrderHostingExistingRequest(BaseModel):
    """Request to order hosting for existing HostBay domain (DEPRECATED)"""
    domain_name: str
    plan: str = Field(..., pattern="^(pro_7day|pro_30day)$")
    period: int = Field(1, ge=1, le=12)
    auto_renew: bool = Field(True, description="Enable automatic renewal before expiration")


class OrderHostingExternalRequest(BaseModel):
    """Request to order hosting for external domain (DEPRECATED)"""
    domain_name: str
    plan: str = Field(..., pattern="^(pro_7day|pro_30day)$")
    linking_mode: str = Field(..., pattern="^(smart|manual)$")
    period: int = Field(1, ge=1, le=12)
    auto_renew: bool = Field(True, description="Enable automatic renewal before expiration")


class RenewHostingRequest(BaseModel):
    """Request to renew hosting"""
    period: int = Field(1, ge=1, le=12)
    auto_renew: Optional[bool] = Field(None, description="Update auto-renewal setting (optional)")


class ResetPasswordRequest(BaseModel):
    """Request to reset hosting control panel password"""
    new_password: str = Field(..., min_length=8, max_length=64)


class HostingSubscriptionResponse(BaseModel):
    """Hosting subscription information"""
    id: int
    domain_name: str
    plan: str
    status: str
    username: str = Field(..., description="Hosting control panel username")
    server_ip: str
    auto_renew: bool
    created_at: str
    expires_at: str
    is_active: bool


class HostingCredentialsResponse(BaseModel):
    """Hosting credentials"""
    control_panel_url: str = Field(..., description="Hosting control panel URL")
    username: str = Field(..., description="Hosting control panel username")
    password: str = Field(..., description="Hosting control panel password")
    ftp_host: str
    ftp_port: int


class HostingUsageResponse(BaseModel):
    """Hosting usage statistics"""
    disk_used_mb: float
    disk_limit_mb: float
    bandwidth_used_mb: float
    bandwidth_limit_mb: float
    databases_used: int
    databases_limit: int
    email_accounts_used: int
    email_accounts_limit: int


class AutoRenewalSettingRequest(BaseModel):
    """Request to update auto-renewal setting"""
    auto_renew: bool = Field(..., description="Enable or disable automatic renewal")


class AutoRenewalSettingResponse(BaseModel):
    """Auto-renewal setting response"""
    subscription_id: int
    domain_name: str
    auto_renew: bool
    updated_at: str


# ====================================================================
# Server Info Response Models
# ====================================================================

class ServerLocation(BaseModel):
    """Server physical location details"""
    region: str = Field(..., description="Geographic region (e.g., Russia, Europe, Asia)")
    datacenter: str = Field(..., description="Datacenter city or name")
    country: str = Field(..., description="Country where server is located")
    timezone: str = Field(..., description="Server timezone")
    latency_info: str = Field(..., description="Expected latency for different regions")


class ServerSpecifications(BaseModel):
    """Server hardware and software specifications"""
    control_panel: str = Field(default="HostBay Panel", description="Hosting control panel")
    storage_type: str = Field(default="NVMe SSD", description="Storage technology")
    network_speed: str = Field(default="1 Gbps", description="Network connection speed")
    uptime_guarantee: str = Field(default="99.9%", description="Uptime SLA")
    features: List[str] = Field(..., description="List of included features")


class ServerNameservers(BaseModel):
    """DNS nameservers for the hosting server"""
    primary: str = Field(..., description="Primary nameserver")
    secondary: str = Field(..., description="Secondary nameserver")


class ServerInfoResponse(BaseModel):
    """
    Complete hosting server information for developers.
    
    Use this endpoint to get server details needed for:
    - Configuring DNS records (IP address, nameservers)
    - Understanding server location for latency optimization
    - Displaying server info to end users
    """
    hostname: str = Field(..., description="Server hostname")
    ip_address: str = Field(..., description="Server IP address for A record configuration")
    location: ServerLocation = Field(..., description="Physical server location details")
    specifications: ServerSpecifications = Field(..., description="Server hardware/software specs")
    nameservers: ServerNameservers = Field(..., description="DNS nameservers")
    dns_nameservers: List[str] = Field(
        ..., 
        description="DNS nameservers for domain linking (recommended for external domains)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "hostname": "server.hostbay.com",
                "ip_address": "123.45.67.89",
                "location": {
                    "region": "Russia",
                    "datacenter": "Moscow",
                    "country": "Russian Federation",
                    "timezone": "Europe/Moscow",
                    "latency_info": "Optimal for Eastern Europe and Asia"
                },
                "specifications": {
                    "control_panel": "HostBay Panel",
                    "storage_type": "NVMe SSD",
                    "network_speed": "1 Gbps",
                    "uptime_guarantee": "99.9%",
                    "features": ["Unlimited bandwidth", "Free SSL", "Daily backups"]
                },
                "nameservers": {
                    "primary": "ns1.hostbay.com",
                    "secondary": "ns2.hostbay.com"
                },
                "dns_nameservers": [
                    "ns1.hostbay.com",
                    "ns2.hostbay.com"
                ]
            }
        }
