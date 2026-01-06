"""
Environment Management Module
Handles switching between development, staging, and production environments
"""

import os
import logging
from enum import Enum
from typing import Dict, Any

logger = logging.getLogger(__name__)


class Environment(Enum):
    """Environment types"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class EnvironmentManager:
    """Manages environment detection and configuration"""
    
    def __init__(self):
        self._env = self._detect_environment()
        logger.info(f"🌍 Environment detected: {self._env.value}")
    
    def _detect_environment(self) -> Environment:
        """
        Detect current environment with priority order:
        1. TEST_MODE=1 → test
        2. ENVIRONMENT secret → explicit override
        3. REPLIT_DEPLOYMENT=1 → production
        4. Default → development
        """
        # Test mode takes highest priority
        if os.getenv('TEST_MODE') == '1':
            return Environment.TEST
        
        # Explicit environment override (strip whitespace to handle secrets with trailing spaces)
        env_override = os.getenv('ENVIRONMENT', '').lower().strip()
        if env_override == 'production':
            return Environment.PRODUCTION
        elif env_override == 'staging':
            return Environment.STAGING
        elif env_override == 'development':
            return Environment.DEVELOPMENT
        
        # Auto-detect based on Replit deployment
        if os.getenv('REPLIT_DEPLOYMENT') == '1':
            return Environment.PRODUCTION
        
        # Default to development
        return Environment.DEVELOPMENT
    
    @property
    def current(self) -> Environment:
        """Get current environment"""
        return self._env
    
    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self._env == Environment.PRODUCTION
    
    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self._env == Environment.DEVELOPMENT
    
    @property
    def is_staging(self) -> bool:
        """Check if running in staging"""
        return self._env == Environment.STAGING
    
    @property
    def is_test(self) -> bool:
        """Check if running in test mode"""
        return self._env == Environment.TEST
    
    def get_database_url(self) -> str:
        """
        Get database URL based on environment
        
        Priority:
        1. {ENV}_DATABASE_URL (e.g., PRODUCTION_DATABASE_URL)
        2. DATABASE_URL (default)
        """
        # Check environment-specific database URL
        env_db_key = f"{self._env.value.upper()}_DATABASE_URL"
        env_db_url = os.getenv(env_db_key)
        
        if env_db_url:
            logger.info(f"📊 Using {env_db_key} for database connection")
            return env_db_url
        
        # Fallback to default DATABASE_URL
        default_url = os.getenv('DATABASE_URL')
        if not default_url:
            raise ValueError(f"No database URL found. Set {env_db_key} or DATABASE_URL")
        
        logger.info(f"📊 Using default DATABASE_URL for {self._env.value} environment")
        return default_url
    
    def get_config(self) -> Dict[str, Any]:
        """Get environment-specific configuration"""
        base_config = {
            'environment': self._env.value,
            'debug': self.is_development or self.is_test,
            'database_url': self.get_database_url(),
        }
        
        if self.is_production:
            base_config.update({
                'log_level': 'INFO',
                'enable_analytics': True,
                'strict_error_handling': True,
                'rate_limiting': True,
            })
        elif self.is_staging:
            base_config.update({
                'log_level': 'DEBUG',
                'enable_analytics': False,
                'strict_error_handling': True,
                'rate_limiting': False,
            })
        elif self.is_test:
            base_config.update({
                'log_level': 'DEBUG',
                'enable_analytics': False,
                'strict_error_handling': True,
                'mock_external_services': True,
                'rate_limiting': False,
            })
        else:  # development
            base_config.update({
                'log_level': 'DEBUG',
                'enable_analytics': False,
                'strict_error_handling': False,
                'rate_limiting': False,
            })
        
        return base_config


# Singleton instance
_env_manager = None


def get_environment_manager() -> EnvironmentManager:
    """Get or create environment manager singleton"""
    global _env_manager
    if _env_manager is None:
        _env_manager = EnvironmentManager()
    return _env_manager


def is_production() -> bool:
    """Quick check if running in production"""
    return get_environment_manager().is_production


def is_development() -> bool:
    """Quick check if running in development"""
    return get_environment_manager().is_development


def is_test() -> bool:
    """Quick check if running in test mode"""
    return get_environment_manager().is_test
