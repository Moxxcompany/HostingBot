"""
OpenProvider Multi-Account Manager
Manages multiple OpenProvider accounts with separate token/contact caching per account
"""

import os
import logging
import httpx
import time
import asyncio
from typing import Dict, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class OpenProviderAccountClient:
    """Client for a single OpenProvider account with its own token cache"""
    account_id: int
    account_name: str
    username: str
    password: str
    base_url: str = "https://api.openprovider.eu"
    bearer_token: Optional[str] = None
    token_expiry: float = 0
    token_ttl: int = 3500
    contact_handles: Dict[str, str] = field(default_factory=dict)
    _http_client: Optional[httpx.AsyncClient] = field(default=None, repr=False)
    
    def __post_init__(self):
        self._http_client = None
    
    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
            )
        return self._http_client
    
    async def close(self):
        """Close HTTP client"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None
    
    def is_token_valid(self) -> bool:
        """Check if bearer token is still valid"""
        return self.bearer_token is not None and time.time() < self.token_expiry
    
    async def authenticate(self) -> bool:
        """Authenticate with OpenProvider and get bearer token"""
        try:
            client = await self.get_client()
            
            logger.info(f"🔐 Authenticating OpenProvider account: {self.account_name}")
            
            response = await client.post(
                f"{self.base_url}/v1beta/auth/login",
                json={
                    "username": self.username,
                    "password": self.password
                },
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0 and data.get('data', {}).get('token'):
                    self.bearer_token = data['data']['token']
                    self.token_expiry = time.time() + self.token_ttl
                    logger.info(f"✅ OpenProvider authentication successful for {self.account_name}")
                    return True
            
            logger.error(f"❌ OpenProvider authentication failed for {self.account_name}: {response.text}")
            return False
            
        except Exception as e:
            logger.error(f"❌ OpenProvider authentication error for {self.account_name}: {e}")
            return False
    
    async def ensure_authenticated(self) -> bool:
        """Ensure we have a valid token, refreshing if needed"""
        if not self.is_token_valid():
            return await self.authenticate()
        return True
    
    async def api_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Make an authenticated API request"""
        if not await self.ensure_authenticated():
            return None
        
        try:
            client = await self.get_client()
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.bearer_token}'
            }
            
            url = f"{self.base_url}{endpoint}"
            
            if method.upper() == 'GET':
                response = await client.get(url, headers=headers, params=params)
            elif method.upper() == 'POST':
                response = await client.post(url, headers=headers, json=data)
            elif method.upper() == 'PUT':
                response = await client.put(url, headers=headers, json=data)
            elif method.upper() == 'DELETE':
                response = await client.delete(url, headers=headers, params=params)
            else:
                logger.error(f"Unsupported HTTP method: {method}")
                return None
            
            if response.status_code == 200:
                return response.json()
            
            logger.error(f"API request failed: {response.status_code} - {response.text}")
            return None
            
        except Exception as e:
            logger.error(f"API request error: {e}")
            return None
    
    def get_cached_contact_handle(self, tld: str, contact_type: str) -> Optional[str]:
        """Get cached contact handle"""
        key = f"{tld}:{contact_type}"
        return self.contact_handles.get(key)
    
    def cache_contact_handle(self, tld: str, contact_type: str, handle: str):
        """Cache a contact handle"""
        key = f"{tld}:{contact_type}"
        self.contact_handles[key] = handle
        logger.debug(f"Cached contact handle for {self.account_name}: {key} = {handle}")


class OpenProviderAccountManager:
    """
    Manages multiple OpenProvider accounts with per-account token and contact caching.
    Provides routing logic to select which account to use for operations.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._accounts: Dict[int, OpenProviderAccountClient] = {}
        self._default_account_id: Optional[int] = None
        self._initialized = True
        logger.info("🏢 OpenProvider Account Manager initialized")
    
    async def load_accounts_from_db(self) -> bool:
        """Load accounts from database and initialize clients"""
        try:
            from database import get_openprovider_accounts, get_all_contact_handles_for_account
            
            accounts = await get_openprovider_accounts()
            if not accounts:
                logger.warning("⚠️ No OpenProvider accounts found in database")
                return False
            
            for account in accounts:
                account_id = account['id']
                account_name = account['account_name']
                username = account['username']
                is_default = account.get('is_default', False)
                
                password = self._get_password_for_account(account_name, username)
                if not password:
                    logger.error(f"❌ No password found for account: {account_name}")
                    continue
                
                client = OpenProviderAccountClient(
                    account_id=account_id,
                    account_name=account_name,
                    username=username,
                    password=password
                )
                
                handles = await get_all_contact_handles_for_account(account_id)
                for h in handles:
                    client.cache_contact_handle(h['tld'], h['contact_type'], h['handle'])
                
                self._accounts[account_id] = client
                
                if is_default:
                    self._default_account_id = account_id
                
                logger.info(f"✅ Loaded OpenProvider account: {account_name} (ID: {account_id}, handles: {len(handles)})")
            
            if not self._default_account_id and self._accounts:
                self._default_account_id = next(iter(self._accounts.keys()))
                logger.info(f"ℹ️ No default account set, using first account (ID: {self._default_account_id})")
            
            logger.info(f"✅ Loaded {len(self._accounts)} OpenProvider accounts")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to load OpenProvider accounts: {e}")
            return False
    
    def _get_password_for_account(self, account_name: str, username: str) -> Optional[str]:
        """Get password for an account from environment variables"""
        if account_name == "Primary" or account_name.lower() == "primary":
            return os.getenv('OPENPROVIDER_PASSWORD')
        elif account_name == "Secondary" or account_name.lower() == "secondary":
            return os.getenv('Openprovider_pass2')
        
        primary_user = os.getenv('OPENPROVIDER_USERNAME') or os.getenv('OPENPROVIDER_EMAIL')
        if username == primary_user:
            return os.getenv('OPENPROVIDER_PASSWORD')
        
        secondary_user = os.getenv('Openprovider_user2')
        if username == secondary_user:
            return os.getenv('Openprovider_pass2')
        
        return None
    
    def get_account(self, account_id: Optional[int] = None) -> Optional[OpenProviderAccountClient]:
        """Get an account client by ID, or the default account"""
        if account_id is not None:
            return self._accounts.get(account_id)
        
        if self._default_account_id:
            return self._accounts.get(self._default_account_id)
        
        if self._accounts:
            return next(iter(self._accounts.values()))
        
        return None
    
    def get_default_account(self) -> Optional[OpenProviderAccountClient]:
        """Get the default account client"""
        return self.get_account(self._default_account_id)
    
    def get_all_accounts(self) -> Dict[int, OpenProviderAccountClient]:
        """Get all loaded accounts"""
        return self._accounts
    
    async def authenticate_all(self) -> Dict[int, bool]:
        """Authenticate all accounts"""
        results = {}
        for account_id, client in self._accounts.items():
            try:
                results[account_id] = await client.authenticate()
            except Exception as e:
                logger.error(f"Failed to authenticate account {account_id}: {e}")
                results[account_id] = False
        return results
    
    async def close_all(self):
        """Close all HTTP clients"""
        for client in self._accounts.values():
            await client.close()
    
    def set_default_account(self, account_id: int) -> bool:
        """Set the default account"""
        if account_id in self._accounts:
            self._default_account_id = account_id
            logger.info(f"✅ Default account set to ID: {account_id}")
            return True
        logger.error(f"❌ Account ID {account_id} not found")
        return False


_account_manager: Optional[OpenProviderAccountManager] = None


def get_account_manager() -> OpenProviderAccountManager:
    """Get or create the singleton account manager"""
    global _account_manager
    if _account_manager is None:
        _account_manager = OpenProviderAccountManager()
    return _account_manager


async def initialize_account_manager() -> bool:
    """Initialize and load accounts into the manager"""
    manager = get_account_manager()
    success = await manager.load_accounts_from_db()
    
    if success:
        auth_results = await manager.authenticate_all()
        authenticated = sum(1 for v in auth_results.values() if v)
        logger.info(f"✅ OpenProvider Account Manager: {authenticated}/{len(auth_results)} accounts authenticated")
    
    return success


def get_openprovider_service_for_account(account_id: Optional[int] = None):
    """
    Get an OpenProviderService instance configured for a specific account.
    
    This creates a new service instance with the account's credentials,
    allowing account-specific domain operations.
    
    Args:
        account_id: The account ID to use, or None for default account
        
    Returns:
        OpenProviderService instance configured for the account, or None if account not found
    """
    from services.openprovider import OpenProviderService
    
    manager = get_account_manager()
    
    # If no account_id specified, use the default account
    if account_id is None:
        account_id = manager._default_account_id
        if account_id is None:
            # No default set yet, use standard OpenProviderService
            logger.debug("No default account set, using standard OpenProviderService")
            return OpenProviderService()
    
    account = manager.get_account(account_id)
    
    if not account:
        logger.warning(f"⚠️ Account {account_id} not found, using default OpenProviderService")
        return OpenProviderService()
    
    service = OpenProviderService.__new__(OpenProviderService)
    service._initialized = True
    service.username = account.username
    service.password = account.password
    service.base_url = account.base_url
    service.bearer_token = account.bearer_token
    service.headers = {'Content-Type': 'application/json'}
    service._client = None
    service._account_id = account.account_id
    
    logger.info(f"🔧 Created OpenProviderService for account: {account.account_name} (ID: {account.account_id})")
    return service


def get_default_account_id() -> Optional[int]:
    """Get the default account ID"""
    manager = get_account_manager()
    return manager._default_account_id


async def get_account_id_for_domain(domain_name: str) -> Optional[int]:
    """
    Get the account ID associated with a domain.
    
    Args:
        domain_name: The domain name to look up
        
    Returns:
        The provider_account_id from the domains table, or None if not found
    """
    try:
        from database import execute_query
        
        result = await execute_query(
            "SELECT provider_account_id FROM domains WHERE domain_name = %s",
            (domain_name,)
        )
        
        if result and result[0].get('provider_account_id'):
            return result[0]['provider_account_id']
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Error looking up account for domain {domain_name}: {e}")
        return None


async def list_domains_for_account(account_id: int) -> list:
    """
    List all domains registered under a specific account.
    
    Args:
        account_id: The OpenProvider account ID
        
    Returns:
        List of domain records
    """
    try:
        from database import execute_query
        
        result = await execute_query(
            """SELECT domain_name, status, created_at 
               FROM domains 
               WHERE provider_account_id = %s 
               ORDER BY created_at DESC""",
            (account_id,)
        )
        
        return result or []
        
    except Exception as e:
        logger.error(f"❌ Error listing domains for account {account_id}: {e}")
        return []
