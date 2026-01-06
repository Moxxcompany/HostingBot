"""
Domain management schemas.
"""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class ContactInfo(BaseModel):
    """Contact information for domain registration"""
    first_name: str = Field(..., min_length=1, max_length=100, examples=["John"])
    last_name: str = Field(..., min_length=1, max_length=100, examples=["Smith"])
    email: str = Field(..., pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', examples=["john.smith@example.com"])
    phone: str = Field(..., description="Format: +1.5551234567", examples=["+1.5551234567"])
    company: Optional[str] = Field(None, max_length=100, examples=["Acme Corporation"])
    address: str = Field(..., min_length=1, max_length=200, examples=["123 Main Street"])
    city: str = Field(..., min_length=1, max_length=100, examples=["San Francisco"])
    state: Optional[str] = Field(None, max_length=100, examples=["CA"])
    postal_code: str = Field(..., min_length=1, max_length=20, examples=["94102"])
    country: str = Field(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2 code", examples=["US"])
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "first_name": "John",
                    "last_name": "Smith",
                    "email": "john.smith@example.com",
                    "phone": "+1.5551234567",
                    "company": "Acme Corporation",
                    "address": "123 Main Street",
                    "city": "San Francisco",
                    "state": "CA",
                    "postal_code": "94102",
                    "country": "US"
                }
            ]
        }
    }


class RegisterDomainRequest(BaseModel):
    """Request to register a domain"""
    domain_name: str = Field(..., pattern=r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,}$', examples=["example.com"])
    period: int = Field(1, ge=1, le=10, description="Registration period in years", examples=[1])
    auto_renew: bool = Field(True, description="Enable auto-renewal", examples=[True])
    contacts: Optional[Dict[str, ContactInfo]] = Field(None, description="registrant, admin, tech, billing contacts (required if use_hostbay_contacts=false)")
    use_hostbay_contacts: bool = Field(False, description="Use HostBay's default contacts (no contact info required)", examples=[True])
    nameservers: Optional[List[str]] = Field(None, max_length=4, description="Custom nameservers", examples=[["ns1.hostbay.io", "ns2.hostbay.io"]])
    privacy_protection: bool = Field(False, description="Enable WHOIS privacy", examples=[False])
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "domain_name": "example.com",
                    "period": 1,
                    "auto_renew": True,
                    "use_hostbay_contacts": True,
                    "privacy_protection": False
                }
            ]
        }
    }
    
    @model_validator(mode='after')
    def validate_contacts(self):
        """Ensure either contacts or use_hostbay_contacts is provided"""
        if not self.use_hostbay_contacts and not self.contacts:
            raise ValueError("Either 'contacts' must be provided or 'use_hostbay_contacts' must be true")
        if self.use_hostbay_contacts and self.contacts:
            raise ValueError("Cannot specify both 'contacts' and 'use_hostbay_contacts=true'. Choose one option.")
        return self


class BulkRegisterRequest(BaseModel):
    """Request to register multiple domains"""
    domains: List[RegisterDomainRequest] = Field(..., min_items=1, max_items=50)


class TransferDomainRequest(BaseModel):
    """Request to transfer a domain"""
    domain_name: str
    auth_code: str = Field(..., description="EPP/Auth code from current registrar")
    period: int = Field(1, ge=1, le=10)
    auto_renew: bool = True


class RenewDomainRequest(BaseModel):
    """Request to renew a domain"""
    period: int = Field(1, ge=1, le=10, description="Renewal period in years")


class UpdateContactsRequest(BaseModel):
    """Request to update domain contacts"""
    registrant: Optional[ContactInfo] = None
    admin: Optional[ContactInfo] = None
    tech: Optional[ContactInfo] = None
    billing: Optional[ContactInfo] = None


class DomainResponse(BaseModel):
    """Domain information response"""
    domain_name: str
    status: str
    created_at: str
    expires_at: str
    updated_at: Optional[str]
    registry_id: Optional[str] = Field(None, description="Domain registry identifier")
    dns_zone_id: Optional[str] = Field(None, description="DNS zone identifier")
    auto_renew: bool
    privacy_protection: bool
    is_locked: bool


class DomainListResponse(BaseModel):
    """List of domains"""
    domains: List[DomainResponse]
    total: int
