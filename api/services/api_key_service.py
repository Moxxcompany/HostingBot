"""
API Key management service.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from database import execute_query, execute_update
from api.utils.crypto import generate_api_key, hash_api_key, verify_api_key

logger = logging.getLogger(__name__)


class APIKeyService:
    """Service for managing API keys"""
    
    @staticmethod
    async def create_api_key(
        user_id: int,
        name: str,
        permissions: Optional[Dict[str, Any]] = None,
        rate_limit_per_hour: int = 1000,
        rate_limit_per_day: int = 10000,
        expires_in_days: Optional[int] = None,
        ip_whitelist: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a new API key.
        
        Args:
            user_id: User ID
            name: Key name/description
            permissions: Permission dictionary
            rate_limit_per_hour: Hourly rate limit
            rate_limit_per_day: Daily rate limit
            expires_in_days: Days until expiration (None = never)
            ip_whitelist: List of allowed IPs
        
        Returns:
            Dictionary with key details (full key shown only once)
        """
        full_key, key_prefix = generate_api_key()
        key_hash = hash_api_key(full_key)
        
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now() + timedelta(days=expires_in_days)
        
        import json
        result = await execute_query("""
            INSERT INTO api_keys (
                user_id, key_hash, key_prefix, name, permissions,
                rate_limit_per_hour, rate_limit_per_day, expires_at, ip_whitelist
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
            RETURNING id, key_prefix, name, permissions, rate_limit_per_hour,
                      rate_limit_per_day, created_at, expires_at, is_active
        """, (
            user_id, key_hash, key_prefix, name,
            json.dumps(permissions or {}),
            rate_limit_per_hour, rate_limit_per_day,
            expires_at, json.dumps(ip_whitelist or [])
        ))
        
        if result:
            key_data = result[0]
            logger.info(f"✅ API key created: {key_prefix} for user {user_id}")
            return {
                "id": key_data['id'],
                "key": full_key,
                "key_prefix": key_data['key_prefix'],
                "name": key_data['name'],
                "permissions": key_data['permissions'],
                "rate_limit_per_hour": key_data['rate_limit_per_hour'],
                "rate_limit_per_day": key_data['rate_limit_per_day'],
                "created_at": key_data['created_at'].isoformat() if key_data.get('created_at') else None,
                "expires_at": key_data['expires_at'].isoformat() if key_data.get('expires_at') else None,
                "is_active": key_data['is_active']
            }
        
        raise Exception("Failed to create API key")
    
    @staticmethod
    async def validate_api_key(api_key: str) -> Optional[Dict[str, Any]]:
        """
        Validate API key and return key details.
        
        Args:
            api_key: Plain text API key
        
        Returns:
            Key details if valid, None otherwise
        """
        key_hash = hash_api_key(api_key)
        
        result = await execute_query("""
            SELECT id, user_id, key_prefix, name, environment, permissions,
                   rate_limit_per_hour, rate_limit_per_day,
                   ip_whitelist, expires_at, is_active
            FROM api_keys
            WHERE key_hash = %s
        """, (key_hash,))
        
        if not result:
            return None
        
        key_data = result[0]
        
        # Check if API key is active
        if not key_data.get('is_active'):
            logger.warning(f"⚠️ API key is inactive: {key_data['key_prefix']}")
            return None
        
        # Check if API key has expired
        if key_data.get('expires_at') and key_data['expires_at'] < datetime.now():
            logger.warning(f"⚠️ API key expired: {key_data['key_prefix']}")
            return None
        
        await execute_update("""
            UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = %s
        """, (key_data['id'],))
        
        return {
            "id": key_data['id'],
            "user_id": key_data['user_id'],
            "key_prefix": key_data['key_prefix'],
            "name": key_data['name'],
            "environment": key_data['environment'],
            "permissions": key_data['permissions'],
            "rate_limit_per_hour": key_data['rate_limit_per_hour'],
            "rate_limit_per_day": key_data['rate_limit_per_day'],
            "ip_whitelist": key_data.get('ip_whitelist')
        }
    
    @staticmethod
    async def list_api_keys(user_id: int, include_revoked: bool = False) -> List[Dict[str, Any]]:
        """List all API keys for a user"""
        query = """
            SELECT id, key_prefix, name, permissions,
                   rate_limit_per_hour, rate_limit_per_day,
                   created_at, last_used_at, expires_at,
                   is_active, revoked_at, revoked_reason
            FROM api_keys
            WHERE user_id = %s
        """
        
        if not include_revoked:
            query += " AND is_active = true AND revoked_at IS NULL"
        
        query += " ORDER BY created_at DESC"
        
        results = await execute_query(query, (user_id,))
        
        keys = []
        for row in results:
            keys.append({
                "id": row['id'],
                "key_prefix": row['key_prefix'],
                "name": row['name'],
                "permissions": row['permissions'],
                "rate_limit_per_hour": row['rate_limit_per_hour'],
                "rate_limit_per_day": row['rate_limit_per_day'],
                "created_at": row['created_at'].isoformat() if row.get('created_at') else None,
                "last_used_at": row['last_used_at'].isoformat() if row.get('last_used_at') else None,
                "expires_at": row['expires_at'].isoformat() if row.get('expires_at') else None,
                "is_active": row['is_active'],
                "revoked_at": row['revoked_at'].isoformat() if row.get('revoked_at') else None,
                "revoked_reason": row.get('revoked_reason')
            })
        
        return keys
    
    @staticmethod
    async def revoke_api_key(key_id: int, user_id: int, reason: str = "User requested") -> bool:
        """Revoke an API key"""
        result = await execute_update("""
            UPDATE api_keys
            SET is_active = false, revoked_at = CURRENT_TIMESTAMP, revoked_reason = %s
            WHERE id = %s AND user_id = %s
            RETURNING id
        """, (reason, key_id, user_id))
        
        if result:
            logger.info(f"✅ API key revoked: ID {key_id} for user {user_id}")
            return True
        
        return False
    
    @staticmethod
    async def update_api_key(
        key_id: int,
        user_id: int,
        name: Optional[str] = None,
        permissions: Optional[Dict] = None,
        rate_limit_per_hour: Optional[int] = None,
        rate_limit_per_day: Optional[int] = None
    ) -> bool:
        """Update API key settings"""
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = %s")
            params.append(name)
        
        if permissions is not None:
            updates.append("permissions = %s")
            params.append(permissions)
        
        if rate_limit_per_hour is not None:
            updates.append("rate_limit_per_hour = %s")
            params.append(rate_limit_per_hour)
        
        if rate_limit_per_day is not None:
            updates.append("rate_limit_per_day = %s")
            params.append(rate_limit_per_day)
        
        if not updates:
            return False
        
        params.extend([key_id, user_id])
        
        query = f"""
            UPDATE api_keys
            SET {', '.join(updates)}
            WHERE id = %s AND user_id = %s
            RETURNING id
        """
        
        result = await execute_update(query, tuple(params))
        return bool(result)
