"""
Nameserver management schemas.
"""
from typing import List
from pydantic import BaseModel, Field, ConfigDict


class UpdateNameserversRequest(BaseModel):
    """Request to update nameservers"""
    
    nameservers: List[str] = Field(
        min_items=2, 
        max_items=4, 
        description="List of nameserver hostnames (2-4 required). Enter as JSON array: [\"your-ns1.example.com\", \"your-ns2.example.com\"]"
    )


class NameserversResponse(BaseModel):
    """Nameservers response"""
    domain: str
    nameservers: List[str]
    provider: str
    provider_name: str
    is_cloudflare: bool
    last_updated: str


class NameserverAnalysisResponse(BaseModel):
    """Nameserver analysis response"""
    current_nameservers: List[str]
    provider: str
    is_ready_for_hosting: bool
    recommendations: List[str]


class NameserverVerificationResponse(BaseModel):
    """Nameserver verification response"""
    propagated: bool
    nameservers_detected: List[str]
    matches_expected: bool
    check_timestamp: str


class NameserverPresetsResponse(BaseModel):
    """Available nameserver presets"""
    cloudflare: List[str]
    hosting: List[str]
