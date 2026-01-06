"""
API key authentication middleware.
"""
import logging
import time
from fastapi import Request, Header
from typing import Optional
from api.services.api_key_service import APIKeyService
from api.utils.errors import AuthenticationError, PermissionDeniedError

logger = logging.getLogger(__name__)


async def get_api_key_from_header(authorization: Optional[str] = Header(None)) -> dict:
    """
    Extract and validate API key from Authorization header.
    
    Expected format: Bearer hbay_live_Ak7mN9pQr2tXvYz4bC6dE8fG1hJ3kL5nP
    
    Returns:
        API key details dictionary
    
    Raises:
        AuthenticationError: If key is missing or invalid
    """
    if not authorization:
        raise AuthenticationError("Missing Authorization header")
    
    parts = authorization.split()
    
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthenticationError("Invalid Authorization header format. Use: Bearer <api_key>")
    
    api_key = parts[1]
    
    if not api_key.startswith("hbay_"):
        raise AuthenticationError("Invalid API key format")
    
    key_data = await APIKeyService.validate_api_key(api_key)
    
    if not key_data:
        raise AuthenticationError("Invalid or expired API key")
    
    return key_data


def check_permission(key_data: dict, resource: str, action: str = "read"):
    """
    Check if API key has permission for resource/action.
    
    Args:
        key_data: API key data dictionary
        resource: Resource name (domains, dns, hosting, etc.)
        action: Action type (read, write)
    
    Raises:
        PermissionDeniedError: If permission is denied
    """
    permissions = key_data.get("permissions", {})
    
    if resource not in permissions:
        raise PermissionDeniedError(
            f"API key does not have permission for resource: {resource}",
            details={"resource": resource, "action": action}
        )
    
    resource_perms = permissions[resource]
    
    if action == "write" and not resource_perms.get("write", False):
        raise PermissionDeniedError(
            f"API key does not have write permission for: {resource}",
            details={"resource": resource, "action": action}
        )
    
    if not resource_perms.get("read", False):
        raise PermissionDeniedError(
            f"API key does not have read permission for: {resource}",
            details={"resource": resource, "action": action}
        )


async def verify_ip_whitelist(request: Request, key_data: dict):
    """
    Verify request IP is in whitelist (if configured).
    
    Args:
        request: FastAPI request object
        key_data: API key data dictionary
    
    Raises:
        PermissionDeniedError: If IP is not whitelisted
    """
    ip_whitelist = key_data.get("ip_whitelist", [])
    
    if not ip_whitelist:
        return
    
    client_ip = request.client.host if request.client else None
    
    if not client_ip:
        raise PermissionDeniedError("Could not determine client IP")
    
    import ipaddress
    
    client_ip_obj = ipaddress.ip_address(client_ip)
    
    allowed = False
    for allowed_ip in ip_whitelist:
        try:
            if '/' in allowed_ip:
                network = ipaddress.ip_network(allowed_ip, strict=False)
                if client_ip_obj in network:
                    allowed = True
                    break
            else:
                if client_ip == allowed_ip:
                    allowed = True
                    break
        except ValueError:
            logger.warning(f"Invalid IP whitelist entry: {allowed_ip}")
    
    if not allowed:
        raise PermissionDeniedError(
            "IP address not in whitelist",
            details={"client_ip": client_ip, "whitelist": ip_whitelist}
        )
