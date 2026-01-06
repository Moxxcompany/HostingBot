"""
Domain Linking Configuration Constants - Phase 1 Foundation
Central configuration for domain linking features

This module provides:
- Domain linking configuration constants
- Nameserver configuration settings
- Timeout and polling interval settings
- Error message templates
"""

from typing import Dict, List, Any
from datetime import timedelta

# ====================================================================
# NAMESERVER CONFIGURATION
# ====================================================================

# Cloudflare nameservers (users point their domains to these at their registrar)
# These are actual Cloudflare nameservers that route to our cPanel hosting
CLOUDFLARE_NAMESERVERS = [
    "anderson.ns.cloudflare.com",
    "leanna.ns.cloudflare.com"
]

# Legacy nameservers (kept for backward compatibility)
HOSTBAY_NAMESERVERS = [
    "anderson.ns.cloudflare.com",
    "leanna.ns.cloudflare.com"
]

# Backup nameservers (for redundancy)
HOSTBAY_BACKUP_NAMESERVERS = [
    "anderson.ns.cloudflare.com",
    "leanna.ns.cloudflare.com"
]

# ====================================================================
# TIMEOUT AND POLLING SETTINGS
# ====================================================================

# DNS propagation timeouts
DNS_PROPAGATION_TIMEOUT = timedelta(hours=24)
DNS_CHECK_INTERVAL = timedelta(minutes=5)
DNS_INITIAL_CHECK_DELAY = timedelta(minutes=2)

# Verification timeouts
VERIFICATION_TIMEOUT = timedelta(hours=48)
VERIFICATION_RETRY_INTERVAL = timedelta(minutes=10)
MAX_VERIFICATION_RETRIES = 50

# Workflow timeouts
WORKFLOW_COMPLETION_TIMEOUT = timedelta(hours=72)
WORKFLOW_STEP_TIMEOUT = timedelta(hours=2)

# ====================================================================
# LINKING STRATEGIES
# ====================================================================

# Available linking strategies
LINKING_STRATEGIES = {
    'smart_mode': {
        'name': 'Smart Mode',
        'description': 'Automatic nameserver changes with guided setup',
        'estimated_time': '5-15 minutes',
        'difficulty': 'easy',
        'requires_user_action': True
    },
    'manual_dns': {
        'name': 'Manual DNS',
        'description': 'Keep current nameservers with manual DNS configuration',
        'estimated_time': '10-30 minutes', 
        'difficulty': 'medium',
        'requires_user_action': True
    },
    'already_linked': {
        'name': 'Already Linked',
        'description': 'Domain already using HostBay nameservers',
        'estimated_time': '1-2 minutes',
        'difficulty': 'none',
        'requires_user_action': False
    }
}

# Default strategy
DEFAULT_LINKING_STRATEGY = 'smart_mode'

# ====================================================================
# PROGRESS TRACKING
# ====================================================================

# Progress percentages for different workflow states
WORKFLOW_PROGRESS = {
    'initiated': 5,
    'analyzing_domain': 15,
    'awaiting_user_choice': 25,
    'configuring_dns': 35,
    'verifying_nameservers': 50,
    'verifying_ownership': 70,
    'provisioning_hosting': 85,
    'completed': 100,
    'failed': 0,
    'cancelled': 0
}

# Progress steps for UI display
WORKFLOW_STEPS = {
    'initiated': 'Starting domain analysis...',
    'analyzing_domain': 'Analyzing domain configuration...',
    'awaiting_user_choice': 'Waiting for your confirmation...',
    'configuring_dns': 'Configuring DNS settings...',
    'verifying_nameservers': 'Verifying nameserver changes...',
    'verifying_ownership': 'Verifying domain ownership...',
    'provisioning_hosting': 'Setting up hosting integration...',
    'completed': 'Domain linking completed successfully!',
    'failed': 'Domain linking failed',
    'cancelled': 'Domain linking cancelled'
}

# ====================================================================
# ERROR MESSAGE TEMPLATES
# ====================================================================

ERROR_MESSAGES = {
    # DNS Analysis Errors
    'dns_lookup_failed': "❌ <b>DNS Lookup Failed</b>\n\nCould not retrieve DNS information for {domain_name}.\nPlease check that the domain is properly configured and try again.",
    
    'domain_not_found': "❌ <b>Domain Not Found</b>\n\n{domain_name} could not be found in DNS.\nPlease verify the domain name and try again.",
    
    'nameserver_timeout': "⏰ <b>Nameserver Timeout</b>\n\nTimeout while checking nameservers for {domain_name}.\nThis may be temporary - please try again in a few minutes.",
    
    # Ownership Verification Errors
    'ownership_verification_failed': "❌ <b>Ownership Verification Failed</b>\n\nCould not verify that you own {domain_name}.\nPlease ensure the verification record is correctly configured.",
    
    'verification_token_not_found': "❌ <b>Verification Token Missing</b>\n\nThe required DNS TXT record was not found for {domain_name}.\n\nPlease add this TXT record:\n<code>_hostbay-verify.{domain_name} TXT {token}</code>",
    
    'verification_expired': "⏰ <b>Verification Expired</b>\n\nThe verification process for {domain_name} has expired.\nPlease start the domain linking process again.",
    
    # Configuration Errors
    'nameserver_change_failed': "❌ <b>Nameserver Change Failed</b>\n\nCould not detect nameserver changes for {domain_name}.\nPlease ensure you've updated the nameservers at your domain registrar.",
    
    'dns_propagation_timeout': "⏰ <b>DNS Propagation Timeout</b>\n\nDNS changes for {domain_name} are taking longer than expected.\nThis can take up to 24-48 hours in some cases.",
    
    'cloudflare_conflict': "⚠️ <b>Cloudflare Detected</b>\n\n{domain_name} appears to be using Cloudflare.\nThis requires manual DNS configuration instead of nameserver changes.",
    
    # Workflow Errors
    'workflow_timeout': "⏰ <b>Process Timeout</b>\n\nThe domain linking process for {domain_name} has timed out.\nPlease try starting the process again.",
    
    'hosting_integration_failed': "❌ <b>Hosting Integration Failed</b>\n\nCould not complete hosting setup for {domain_name}.\nPlease contact support for assistance.",
    
    'invalid_domain_format': "❌ <b>Invalid Domain</b>\n\n{domain_name} is not a valid domain name.\nPlease enter a valid domain (e.g., example.com).",
    
    # General Errors
    'system_error': "❌ <b>System Error</b>\n\nAn unexpected error occurred while processing {domain_name}.\nPlease try again or contact support if the problem persists.",
    
    'rate_limit_exceeded': "⏰ <b>Rate Limit</b>\n\nToo many requests for {domain_name}.\nPlease wait a few minutes before trying again."
}

# Success message templates
SUCCESS_MESSAGES = {
    'analysis_complete': "✅ <b>Analysis Complete</b>\n\nDomain analysis for {domain_name} is complete.\nRecommended strategy: {strategy}",
    
    'nameserver_verified': "✅ <b>Nameservers Updated</b>\n\n{domain_name} is now using HostBay nameservers.\nDNS changes may take up to 24 hours to fully propagate.",
    
    'ownership_verified': "✅ <b>Ownership Verified</b>\n\nSuccessfully verified that you own {domain_name}.",
    
    'linking_complete': "🎉 <b>Domain Linked Successfully!</b>\n\n{domain_name} is now linked to your HostBay hosting.\nYour website should be accessible within a few minutes.",
    
    'dns_configured': "✅ <b>DNS Configured</b>\n\nDNS settings for {domain_name} have been configured.\nChanges will take effect within 5-10 minutes."
}

# ====================================================================
# UI/UX CONFIGURATION
# ====================================================================

# Button text constants
BUTTONS = {
    'start_linking': "🔗 Start Linking",
    'continue_process': "▶️ Continue",
    'cancel_linking': "❌ Cancel",
    'retry_step': "🔄 Retry",
    'view_progress': "📊 View Progress",
    'back_to_domains': "⬅️ Back to Domains",
    'contact_support': "💬 Contact Support",
    'copy_instructions': "📋 Copy Instructions",
    'check_status': "🔍 Check Status",
    'manual_setup': "⚙️ Manual Setup",
    'smart_setup': "🤖 Smart Setup"
}

# Notification settings
NOTIFICATIONS = {
    'send_progress_updates': True,
    'send_completion_notification': True,
    'send_failure_notification': True,
    'progress_update_interval': timedelta(minutes=10)
}

# ====================================================================
# VALIDATION RULES
# ====================================================================

# Domain validation rules
DOMAIN_VALIDATION = {
    'min_length': 3,
    'max_length': 253,
    'allowed_characters': r'^[a-zA-Z0-9.-]+$',
    'blocked_tlds': ['localhost', 'test', 'invalid'],
    'require_tld': True
}

# Nameserver validation
NAMESERVER_VALIDATION = {
    'timeout_seconds': 10,
    'max_retries': 3,
    'require_both_ns': True
}

# ====================================================================
# HELPER FUNCTIONS
# ====================================================================

def get_error_message(error_type: str, **kwargs) -> str:
    """Get formatted error message"""
    template = ERROR_MESSAGES.get(error_type, ERROR_MESSAGES['system_error'])
    return template.format(**kwargs)

def get_success_message(success_type: str, **kwargs) -> str:
    """Get formatted success message"""
    template = SUCCESS_MESSAGES.get(success_type, "✅ Operation completed successfully")
    return template.format(**kwargs)

def get_workflow_progress(state: str) -> int:
    """Get progress percentage for workflow state"""
    return WORKFLOW_PROGRESS.get(state, 0)

def get_workflow_step_description(state: str) -> str:
    """Get user-friendly description for workflow step"""
    return WORKFLOW_STEPS.get(state, "Processing...")

def get_linking_strategy_info(strategy: str) -> Dict[str, Any]:
    """Get information about a linking strategy"""
    return LINKING_STRATEGIES.get(strategy, LINKING_STRATEGIES[DEFAULT_LINKING_STRATEGY])

def validate_domain_name(domain: str) -> Dict[str, Any]:
    """Validate domain name format"""
    import re
    
    if not domain:
        return {'valid': False, 'error': 'Domain name is required'}
    
    if len(domain) < DOMAIN_VALIDATION['min_length']:
        return {'valid': False, 'error': f'Domain must be at least {DOMAIN_VALIDATION["min_length"]} characters'}
    
    if len(domain) > DOMAIN_VALIDATION['max_length']:
        return {'valid': False, 'error': f'Domain cannot exceed {DOMAIN_VALIDATION["max_length"]} characters'}
    
    if not re.match(DOMAIN_VALIDATION['allowed_characters'], domain):
        return {'valid': False, 'error': 'Domain contains invalid characters'}
    
    # Check for TLD
    if DOMAIN_VALIDATION['require_tld'] and '.' not in domain:
        return {'valid': False, 'error': 'Domain must include a TLD (e.g., .com, .org)'}
    
    # Check blocked TLDs
    tld = domain.split('.')[-1].lower()
    if tld in DOMAIN_VALIDATION['blocked_tlds']:
        return {'valid': False, 'error': f'TLD .{tld} is not supported'}
    
    return {'valid': True, 'domain': domain.lower()}