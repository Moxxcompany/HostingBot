"""
DNS management schemas.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class CreateDNSRecordRequest(BaseModel):
    """Request to create DNS record"""
    type: str = Field(..., pattern="^(A|AAAA|CNAME|MX|TXT|NS|SRV)$", description="DNS record type", examples=["A"])
    name: str = Field(..., description="Record name: '@' for root domain, subdomain name for subdomains. Supports custom subdomains for A, CNAME, and TXT records. TXT records can use underscores (e.g., '_dmarc')", examples=["www", "api", "_dmarc", "@"])
    content: str = Field(..., description="Record content/value", examples=["192.0.2.1"])
    ttl: int = Field(300, ge=60, le=86400, description="Time to live in seconds", examples=[300])
    priority: Optional[int] = Field(None, ge=0, le=65535, description="Priority (required for MX, SRV)", examples=[None])
    weight: Optional[int] = Field(None, ge=0, le=65535, description="Weight (required for SRV records)", examples=[None])
    port: Optional[int] = Field(None, ge=1, le=65535, description="Port (required for SRV records)", examples=[None])
    proxied: bool = Field(False, description="Enable Cloudflare proxy (A/AAAA/CNAME only)", examples=[False])
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "type": "A",
                    "name": "www",
                    "content": "192.0.2.1",
                    "ttl": 300,
                    "proxied": False
                },
                {
                    "type": "CNAME",
                    "name": "shop",
                    "content": "shopify.example.com",
                    "ttl": 300,
                    "proxied": False
                },
                {
                    "type": "TXT",
                    "name": "_dmarc",
                    "content": "v=DMARC1; p=none",
                    "ttl": 300,
                    "proxied": False
                }
            ]
        }
    }
    
    def validate_priority_required(self):
        """Validate that priority is required for MX and SRV records"""
        if self.type in ['MX', 'SRV'] and self.priority is None:
            raise ValueError(f'Priority is required for {self.type} records')
        return self


class UpdateDNSRecordRequest(BaseModel):
    """Request to update DNS record"""
    type: str = Field(..., pattern="^(A|AAAA|CNAME|MX|TXT|NS|SRV)$")
    name: str
    content: str
    ttl: int = Field(300, ge=60, le=86400)
    priority: Optional[int] = Field(None, ge=0, le=65535)
    weight: Optional[int] = Field(None, ge=0, le=65535)
    port: Optional[int] = Field(None, ge=1, le=65535)
    proxied: bool = False
    
    def validate_priority_required(self):
        """Validate that priority is required for MX and SRV records"""
        if self.type in ['MX', 'SRV'] and self.priority is None:
            raise ValueError(f'Priority is required for {self.type} records')
        return self


class BulkDNSOperation(BaseModel):
    """Single DNS operation for bulk requests"""
    action: str = Field(..., pattern="^(create|update|delete)$")
    record_id: Optional[str] = None
    type: Optional[str] = None
    name: Optional[str] = None
    content: Optional[str] = None
    ttl: Optional[int] = None
    priority: Optional[int] = None
    proxied: Optional[bool] = None


class BulkDNSRequest(BaseModel):
    """Request to perform bulk DNS operations"""
    operations: List[BulkDNSOperation] = Field(..., min_length=1, max_length=100)


class DNSRecordResponse(BaseModel):
    """DNS record response"""
    id: str
    type: str
    name: str
    content: str
    ttl: int
    priority: Optional[int]
    proxied: bool
    created_at: str
    modified_at: str


class DNSRecordsListResponse(BaseModel):
    """List of DNS records"""
    records: List[DNSRecordResponse]
    total: int
