"""
Service Constants and Validators

Shared constants and validation functions used across the hosting bundle system
to ensure consistency and prevent circular dependencies.
"""

# HOSTING BUNDLE SERVICE TYPE CONSTANTS - Ensures consistency across codebase
# FIXED: Updated to match actual usage in handlers and orchestrator
HOSTING_SERVICE_TYPES = {
    'DOMAIN_BUNDLE': 'hosting_domain_bundle',  # NEW domain registration + hosting
    'EXISTING_DOMAIN': 'hosting_with_existing_domain',  # NO domain registration, existing domain + hosting
    'HOSTING_ONLY': 'hosting_only'  # Hosting only, no domain involved
}

def is_hosting_bundle_service_type(service_type: str) -> bool:
    """Validate if service type represents a hosting bundle"""
    return service_type in [HOSTING_SERVICE_TYPES['DOMAIN_BUNDLE'], HOSTING_SERVICE_TYPES['EXISTING_DOMAIN']]

def get_all_hosting_service_types() -> list:
    """Get list of all valid hosting service types"""
    return list(HOSTING_SERVICE_TYPES.values())


def enforce_hosting_context(domain_status: dict, domain_name: str, context_description: str = "routing decision") -> bool:
    """
    Bulletproof hosting bundle context enforcement guard
    
    This function provides centralized, mandatory hosting context checking
    for all routing decision points to prevent hosting bundle users from
    being redirected to standalone domain registration flows.
    
    Args:
        domain_status: Domain analysis result containing hosting_bundle_context
        domain_name: Domain name being processed
        context_description: Description of where this guard is being used
        
    Returns:
        bool: True if hosting bundle context is enforced, False if not in hosting context
        
    Usage:
        if enforce_hosting_context(domain_status, domain_name, "smart domain handler"):
            # Process within hosting bundle context
            return handle_hosting_flow()
        else:
            # Process as standalone domain operation
            return handle_domain_flow()
    """
    import logging
    logger = logging.getLogger(__name__)
    
    hosting_bundle_context = domain_status.get('hosting_bundle_context', False)
    
    if hosting_bundle_context:
        logger.info(f"🏠 HOSTING CONTEXT ENFORCED: Domain {domain_name} in {context_description} MUST stay in hosting bundle context")
        return True
    else:
        logger.info(f"🔀 STANDALONE ROUTING: Domain {domain_name} in {context_description} proceeding with standalone domain operations")
        return False


def log_routing_enforcement(domain_name: str, context_location: str, hosting_context: bool, action_taken: str):
    """
    Centralized logging for routing enforcement decisions
    
    Args:
        domain_name: Domain being processed
        context_location: Where this enforcement happened (e.g., "smart_domain_handler") 
        hosting_context: Whether hosting context was detected
        action_taken: What action was taken based on context
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if hosting_context:
        logger.info(f"🏠 ROUTING ENFORCEMENT: {domain_name} @ {context_location} → {action_taken} (hosting bundle context)")
    else:
        logger.info(f"🔀 ROUTING ENFORCEMENT: {domain_name} @ {context_location} → {action_taken} (standalone domain context)")