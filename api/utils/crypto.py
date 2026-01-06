"""
Cryptographic utilities for API key generation and hashing.
"""
import hashlib
import secrets
import string
from typing import Tuple


def generate_api_key(prefix: str = "hbay", env: str = "live") -> Tuple[str, str]:
    """
    Generate a secure API key with the format: hbay_live_Ak7mN9pQr2tXvYz4bC6dE8fG1hJ3kL5nP
    
    Args:
        prefix: Key prefix (default: "hbay")
        env: Environment (live/test)
    
    Returns:
        Tuple of (full_key, key_prefix)
        - full_key: Complete API key (shown only once)
        - key_prefix: First 16 chars for display
    """
    alphabet = string.ascii_letters + string.digits
    random_part = ''.join(secrets.choice(alphabet) for _ in range(32))
    
    full_key = f"{prefix}_{env}_{random_part}"
    key_prefix = full_key[:16]
    
    return full_key, key_prefix


def hash_api_key(api_key: str) -> str:
    """
    Hash API key using SHA-256.
    
    Args:
        api_key: Plain text API key
    
    Returns:
        Hexadecimal hash string
    """
    return hashlib.sha256(api_key.encode('utf-8')).hexdigest()


def verify_api_key(plain_key: str, key_hash: str) -> bool:
    """
    Verify an API key against its hash.
    
    Args:
        plain_key: Plain text API key to verify
        key_hash: Stored hash to compare against
    
    Returns:
        True if key matches hash
    """
    computed_hash = hash_api_key(plain_key)
    return secrets.compare_digest(computed_hash, key_hash)
