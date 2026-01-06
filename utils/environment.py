"""Environment detection utilities for production vs development"""

import os
import logging

logger = logging.getLogger(__name__)

def get_webhook_domain() -> str:
    """
    Get the appropriate webhook domain based on environment
    
    Returns:
        str: The domain to use for webhooks
    """
    # CRITICAL FIX: Check ENVIRONMENT variable FIRST to prevent production webhook URLs in development
    # Priority order:
    # 1. ENVIRONMENT=development explicitly set (overrides everything)
    # 2. PRODUCTION_DOMAIN environment variable (Reserved VM production)
    # 3. REPLIT_DEPLOYMENT environment variable (standard deployments)
    # 4. Domain patterns (.janeway.replit.dev = dev, hostbay.replit.app = prod)
    
    # Get current domains
    current_domains = os.getenv('REPLIT_DOMAINS') or os.getenv('REPLIT_DEV_DOMAIN') or ''
    
    # CRITICAL FIX: Check ENVIRONMENT variable first to override PRODUCTION_DOMAIN in dev mode
    environment = os.getenv('ENVIRONMENT', '').lower()
    if environment == 'development':
        # Force development mode even if PRODUCTION_DOMAIN is set
        dev_domain = current_domains or os.getenv('REPLIT_DEV_DOMAIN') or 'localhost:5000'
        logger.info(f"🔧 FORCED DEVELOPMENT MODE - using dev domain: {dev_domain}")
        logger.info(f"🔍 Detection reason: ENVIRONMENT={environment} (overrides PRODUCTION_DOMAIN)")
        return dev_domain
    
    # Check for Reserved VM production domain (only if not forced to development)
    production_domain = os.getenv('PRODUCTION_DOMAIN')
    if production_domain:
        logger.info(f"🌍 Reserved VM production environment detected - using domain: {production_domain}")
        logger.info(f"🔍 Detection reason: PRODUCTION_DOMAIN={production_domain}")
        return production_domain
    
    # Check for other production indicators
    is_production = (
        os.getenv('REPLIT_DEPLOYMENT') is not None or  # Standard deployment
        'hostbay.replit.app' in current_domains or     # Custom domain deployed
        (current_domains and not any(dev_pattern in current_domains 
                                   for dev_pattern in ['.janeway.replit.dev', '.picard.replit.dev', 
                                                      '.kirk.replit.dev', '.data.replit.dev',
                                                      'localhost']))  # Not dev patterns
    )
    
    if is_production:
        # Production deployment - use the custom domain
        domain = 'hostbay.replit.app'
        logger.info(f"🌍 Production environment detected - using domain: {domain}")
        logger.info(f"🔍 Detection reason: REPLIT_DEPLOYMENT={os.getenv('REPLIT_DEPLOYMENT')}, domains={current_domains}")
        return domain
    else:
        # Development environment - use project development domain
        dev_domain = current_domains or os.getenv('REPLIT_DEV_DOMAIN') or 'localhost:5000'
        
        if current_domains:
            logger.info(f"🔧 Development environment detected - using project domain: {dev_domain}")
        else:
            logger.warning("⚠️ No project development domain found, using localhost fallback")
        
        return dev_domain

def get_webhook_url(endpoint: str) -> str:
    """
    Get the complete webhook URL for a specific endpoint
    
    Args:
        endpoint: The endpoint path (e.g., 'telegram', 'dynopay', 'blockbee')
        
    Returns:
        str: Complete webhook URL
    """
    domain = get_webhook_domain()
    protocol = 'http' if domain.startswith('localhost') else 'https'
    url = f"{protocol}://{domain}/webhook/{endpoint}"
    
    return url

def is_production_environment() -> bool:
    """
    Check if we're running in production
    
    Returns:
        bool: True if in production, False if in development
    """
    # CRITICAL FIX: Check ENVIRONMENT variable first to override all other checks
    environment = os.getenv('ENVIRONMENT', '').lower()
    if environment == 'development':
        return False
    elif environment == 'production':
        return True
    
    # Check for Reserved VM production domain
    if os.getenv('PRODUCTION_DOMAIN'):
        return True
    
    # Check for standard deployment
    return os.getenv('REPLIT_DEPLOYMENT') is not None