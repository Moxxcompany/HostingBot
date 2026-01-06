"""
Email Configuration Utility for Domain Registration and Hosting Operations

Provides centralized email configuration with environment variable support
and secure default email for all domain and hosting operations.
"""

import os
import logging

logger = logging.getLogger(__name__)

def get_service_email() -> str:
    """
    Get the configured service email for domain registration and hosting operations.
    
    Uses environment variable HOSTBAY_SERVICE_EMAIL if set, otherwise defaults to
    cloakhost@tutamail.com for all domain and hosting operations.
    
    Returns:
        str: Email address to use for domain registration and hosting account creation
    """
    # Get email from environment variable or use secure default
    service_email = os.getenv('HOSTBAY_SERVICE_EMAIL', 'cloakhost@tutamail.com')
    
    # Validate email format (basic check)
    if '@' not in service_email or '.' not in service_email.split('@')[-1]:
        logger.warning(f"⚠️ Invalid service email format: {service_email}, falling back to default")
        service_email = 'cloakhost@tutamail.com'
    
    logger.debug(f"🔧 Using service email: {service_email}")
    return service_email

def get_admin_email_for_domain(domain_name: str) -> str:
    """
    Get admin email for domain-specific operations.
    
    Args:
        domain_name: Domain name for potential domain-specific email
        
    Returns:
        str: Service email (consistent across all operations)
    """
    # Always use the same service email for consistency
    return get_service_email()

def get_hosting_contact_email(user_id: int = None) -> str:
    """
    Get contact email for hosting account creation.
    
    Args:
        user_id: User ID (not used, kept for compatibility)
        
    Returns:
        str: Service email for hosting contact
    """
    # Always use the same service email for consistency
    return get_service_email()

def log_email_configuration():
    """Log current email configuration for debugging"""
    service_email = get_service_email()
    env_configured = bool(os.getenv('HOSTBAY_SERVICE_EMAIL'))
    
    logger.info(f"📧 EMAIL CONFIG: Service email: {service_email}")
    logger.info(f"📧 EMAIL CONFIG: Environment configured: {env_configured}")
    
    if env_configured:
        logger.info("📧 EMAIL CONFIG: Using custom email from HOSTBAY_SERVICE_EMAIL")
    else:
        logger.info("📧 EMAIL CONFIG: Using default email: cloakhost@tutamail.com")