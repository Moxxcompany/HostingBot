#!/usr/bin/env python3
"""
Centralized Configuration Module for HostBay Telegram Bot
Replaces scattered os.getenv calls with a single source of truth
"""

import os
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from utils.environment_manager import get_environment_manager

logger = logging.getLogger(__name__)

@dataclass
class DatabaseConfig:
    """Database configuration settings"""
    url: str
    max_connections: int = 100
    min_connections: int = 10
    
    @classmethod
    def from_env(cls) -> 'DatabaseConfig':
        """Load database config from environment - automatically selects correct database URL"""
        # ENVIRONMENT-AWARE: Get database URL based on current environment
        # This ensures development uses DEVELOPMENT_DATABASE_URL, production uses PRODUCTION_DATABASE_URL, etc.
        try:
            database_url = get_environment_manager().get_database_url()
        except ValueError:
            # Fallback to empty string if no database URL configured
            database_url = ''
            logger.warning("⚠️ No database URL configured for current environment")
        
        return cls(
            url=database_url,
            max_connections=int(os.getenv('DB_MAX_CONNECTIONS', '100')),
            min_connections=int(os.getenv('DB_MIN_CONNECTIONS', '10'))
        )

@dataclass
class TelegramConfig:
    """Telegram bot configuration"""
    bot_token: str
    webhook_secret_token: Optional[str] = None
    webhook_url: Optional[str] = None
    max_connections: int = 100
    
    @classmethod
    def from_env(cls) -> 'TelegramConfig':
        """Load Telegram config from environment"""
        return cls(
            bot_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
            webhook_secret_token=os.getenv('TELEGRAM_WEBHOOK_SECRET_TOKEN'),
            webhook_url=os.getenv('TELEGRAM_WEBHOOK_URL'),
            max_connections=int(os.getenv('TELEGRAM_MAX_CONNECTIONS', '100'))
        )
    
    def is_valid(self) -> bool:
        """Check if Telegram config is valid"""
        return bool(self.bot_token and len(self.bot_token) > 10)

@dataclass
class PaymentConfig:
    """Payment provider configuration"""
    primary_provider: str = 'blockbee'
    
    # BlockBee
    blockbee_api_key: Optional[str] = None
    
    # DynoPay  
    dynopay_api_key: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> 'PaymentConfig':
        """Load payment config from environment"""
        return cls(
            primary_provider=os.getenv('CRYPTO_PAYMENT_PROVIDER', 'dynopay').lower(),
            blockbee_api_key=os.getenv('BLOCKBEE_API_KEY'),
            dynopay_api_key=os.getenv('DYNOPAY_API_KEY')
        )

@dataclass
class ServiceConfig:
    """External service configuration"""
    # OpenProvider (Domain Registration)
    openprovider_username: Optional[str] = None
    openprovider_password: Optional[str] = None
    
    # Cloudflare (DNS Management)
    cloudflare_api_token: Optional[str] = None
    cloudflare_email: Optional[str] = None
    cloudflare_api_key: Optional[str] = None
    
    # cPanel/WHM (Hosting)
    cpanel_whm_host: Optional[str] = None
    cpanel_whm_username: Optional[str] = None
    cpanel_whm_api_token: Optional[str] = None
    
    # Hosting nameservers configuration
    hosting_nameservers: List[str] = field(default_factory=list)
    
    @classmethod
    def from_env(cls) -> 'ServiceConfig':
        """Load service config from environment"""
        # Parse hosting nameservers from environment
        hosting_nameservers = []
        env_nameservers = os.getenv('HOSTING_NAMESERVERS', '')
        if env_nameservers:
            hosting_nameservers = [ns.strip() for ns in env_nameservers.split(',') if ns.strip()]
        
        # Use production-ready defaults if not configured
        if not hosting_nameservers:
            hosting_nameservers = [
                'ava.ns.cloudflare.com',
                'kai.ns.cloudflare.com'
            ]
        
        return cls(
            openprovider_username=os.getenv('OPENPROVIDER_USERNAME'),
            openprovider_password=os.getenv('OPENPROVIDER_PASSWORD'),
            cloudflare_api_token=os.getenv('CLOUDFLARE_API_TOKEN'),
            cloudflare_email=os.getenv('CLOUDFLARE_EMAIL'),
            cloudflare_api_key=os.getenv('CLOUDFLARE_API_KEY'),
            cpanel_whm_host=os.getenv('CPANEL_WHM_HOST'),
            cpanel_whm_username=os.getenv('CPANEL_WHM_USERNAME'),
            cpanel_whm_api_token=os.getenv('CPANEL_WHM_API_TOKEN'),
            hosting_nameservers=hosting_nameservers
        )

@dataclass  
class AdminConfig:
    """Admin and monitoring configuration"""
    admin_user_ids: list
    alerts_enabled: bool = True
    min_severity: str = 'WARNING'
    
    @classmethod
    def from_env(cls) -> 'AdminConfig':
        """Load admin config from environment"""
        admin_ids_str = os.getenv('ADMIN_USER_IDS', '')
        admin_ids = []
        if admin_ids_str:
            try:
                admin_ids = [int(uid.strip()) for uid in admin_ids_str.split(',') if uid.strip()]
            except ValueError as e:
                logger.warning(f"Invalid ADMIN_USER_IDS format: {e}")
        
        return cls(
            admin_user_ids=admin_ids,
            alerts_enabled=os.getenv('ADMIN_ALERTS_ENABLED', 'true').lower() == 'true',
            min_severity=os.getenv('ADMIN_MIN_SEVERITY', 'WARNING').upper()
        )

@dataclass
class BrandConfig:
    """Brand and customization configuration"""
    platform_name: str = 'HostBay'
    tagline: str = 'Domain & Hosting Services'
    support_contact: str = '@HostBay_support'
    
    @classmethod
    def from_env(cls) -> 'BrandConfig':
        """Load brand config from environment"""
        return cls(
            platform_name=os.getenv('PLATFORM_NAME', 'HostBay'),
            tagline=os.getenv('PLATFORM_TAGLINE', 'Domain & Hosting Services'),
            support_contact=os.getenv('SUPPORT_CONTACT', '@HostBay_support')
        )

@dataclass
class AppConfig:
    """Main application configuration container"""
    database: DatabaseConfig
    telegram: TelegramConfig
    payment: PaymentConfig
    services: ServiceConfig
    admin: AdminConfig
    brand: BrandConfig
    
    # Environment settings
    environment: str
    debug: bool
    test_mode: bool
    
    @classmethod
    def from_env(cls) -> 'AppConfig':
        """Load complete app config from environment"""
        return cls(
            database=DatabaseConfig.from_env(),
            telegram=TelegramConfig.from_env(),
            payment=PaymentConfig.from_env(),
            services=ServiceConfig.from_env(),
            admin=AdminConfig.from_env(),
            brand=BrandConfig.from_env(),
            environment=os.getenv('ENVIRONMENT', 'development'),
            debug=os.getenv('DEBUG', 'false').lower() == 'true',
            test_mode=os.getenv('TEST_MODE', 'false').lower() == 'true'
        )
    
    def validate(self) -> Dict[str, Any]:
        """Validate configuration and return status"""
        issues = []
        warnings = []
        
        # Critical validations (startup-blocking)
        if not self.telegram.is_valid():
            issues.append("TELEGRAM_BOT_TOKEN is required and must be valid")
            
        # Important but non-critical validations (warnings only)
        if not self.database.url:
            warnings.append("DATABASE_URL not configured - database features disabled")
            
        if not self.admin.admin_user_ids:
            warnings.append("ADMIN_USER_IDS not configured - admin functionality limited")
            
        if not self.services.openprovider_username:
            warnings.append("OpenProvider credentials not configured - domain registration disabled")
            
        if not self.payment.blockbee_api_key and not self.payment.dynopay_api_key:
            warnings.append("No payment provider API keys configured - payments disabled")
            
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'environment': self.environment
        }
    
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.environment.lower() in ['production', 'prod']
    
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.environment.lower() in ['development', 'dev']

# Global configuration instance
_config: Optional[AppConfig] = None

def get_config() -> AppConfig:
    """Get global configuration instance (singleton)"""
    global _config
    if _config is None:
        _config = AppConfig.from_env()
        
        # Log validation results
        validation = _config.validate()
        if validation['valid']:
            logger.info(f"✅ Configuration loaded successfully for {validation['environment']} environment")
            if validation['warnings']:
                for warning in validation['warnings']:
                    logger.warning(f"⚠️ Config warning: {warning}")
        else:
            logger.error("❌ Configuration validation failed:")
            for issue in validation['issues']:
                logger.error(f"  • {issue}")
                
    return _config

def reload_config() -> AppConfig:
    """Reload configuration from environment (useful for testing)"""
    global _config
    _config = None
    return get_config()

# Convenience functions for backward compatibility
def get_database_url() -> str:
    """Get database URL"""
    return get_config().database.url

def get_telegram_token() -> str:
    """Get Telegram bot token"""
    return get_config().telegram.bot_token

def get_payment_provider() -> str:
    """Get primary payment provider"""
    return get_config().payment.primary_provider

def is_production() -> bool:
    """Check if running in production"""
    return get_config().is_production()

def is_development() -> bool:
    """Check if running in development"""
    return get_config().is_development()

# Export commonly used configs for easy access
__all__ = [
    'AppConfig', 'DatabaseConfig', 'TelegramConfig', 'PaymentConfig',
    'ServiceConfig', 'AdminConfig', 'BrandConfig', 'get_config',
    'reload_config', 'get_database_url', 'get_telegram_token',
    'get_payment_provider', 'is_production', 'is_development'
]