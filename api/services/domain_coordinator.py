"""
Domain Registration Coordinator for API

This coordinator handles the normalization of contact data for API domain registration,
supporting both HostBay-managed contacts and user-provided contacts.
"""
import logging
import json
from typing import Dict, Any, Optional, List
from api.schemas.domain import ContactInfo, RegisterDomainRequest
from services.openprovider import OpenProviderService
from services.openprovider_manager import get_openprovider_service_for_account, get_default_account_id
from api.constants.privacy_guard import PRIVACY_GUARD_CONTACT_FLAT

logger = logging.getLogger(__name__)


class DomainRegistrationCoordinator:
    """
    Coordinates domain registration between API layer and OpenProviderService.
    
    Handles two registration modes:
    1. HostBay contacts: Uses shared HostBay contact (like bot does)
    2. User contacts: Creates/uses customer-provided contact information
    
    Supports multi-account OpenProvider integration via account_id parameter.
    """
    
    def __init__(self, account_id: Optional[int] = None):
        """
        Initialize coordinator with optional specific OpenProvider account.
        
        Args:
            account_id: The OpenProvider account ID to use, or None for default account
        """
        self.account_id = account_id or get_default_account_id()
        self.openprovider = get_openprovider_service_for_account(self.account_id)
    
    async def register_domain(
        self,
        request: RegisterDomainRequest,
        user_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Register a domain using either HostBay or user-provided contacts.
        
        Args:
            request: Domain registration request with contact mode
            
        Returns:
            Registration result dict with success status and domain data
        """
        try:
            # Step 1: Resolve contact handle and data based on mode
            contact_handle = None
            contact_data = None
            original_contact_data = None
            contact_type = 'hostbay_managed'
            privacy_enabled = False
            
            if request.use_hostbay_contacts:
                # Use HostBay's shared contact (like bot does)
                contact_handle = await self._get_hostbay_contact_handle(request.domain_name)
                if not contact_handle:
                    logger.error(f"❌ Failed to obtain HostBay contact handle for {request.domain_name}")
                    return {
                        'success': False,
                        'error': 'Failed to create or retrieve HostBay contact handle'
                    }
                contact_type = 'hostbay_managed'
                privacy_enabled = request.privacy_protection  # Just track the flag
            else:
                # User-provided contacts
                contact_type = 'user_provided'
                
                if request.privacy_protection:
                    # Privacy enabled: Use Privacy Guard contact, store original
                    logger.info(f"🔒 Privacy enabled - using Privacy Guard contact for {request.domain_name}")
                    
                    # Store original user contact data for future restoration
                    if request.contacts:
                        original_contact_data = json.dumps({
                            role: contact.model_dump() for role, contact in request.contacts.items()
                        })
                    
                    # Convert Privacy Guard dict to ContactInfo object
                    privacy_contact_obj = ContactInfo(**PRIVACY_GUARD_CONTACT_FLAT)
                    privacy_contacts = {
                        'registrant': privacy_contact_obj,
                        'admin': privacy_contact_obj,
                        'tech': privacy_contact_obj,
                        'billing': privacy_contact_obj
                    }
                    contact_handles = await self._create_user_contact_handles(privacy_contacts)
                    privacy_enabled = True
                    
                    logger.info(f"✅ Created Privacy Guard contact handles for {request.domain_name}")
                else:
                    # No privacy: Use user's real contact data
                    contact_handles = await self._create_user_contact_handles(request.contacts)
                    privacy_enabled = False
                
                if not contact_handles or not contact_handles.get('registrant'):
                    logger.error(f"❌ Failed to create contact handles for {request.domain_name}")
                    return {
                        'success': False,
                        'error': 'Failed to create contact handles'
                    }
                
                # Use registrant as primary contact_handle
                contact_handle = contact_handles['registrant']
                
                # Pass all contact handles via tld_additional_params
                contact_data = {
                    'owner_handle': contact_handles.get('registrant'),
                    'admin_handle': contact_handles.get('admin', contact_handles['registrant']),
                    'tech_handle': contact_handles.get('tech', contact_handles['registrant']),
                    'billing_handle': contact_handles.get('billing', contact_handles['registrant'])
                }
            
            # Step 2: Get nameservers (create Cloudflare zone if not provided)
            nameservers = request.nameservers
            cloudflare_zone_id = None
            
            if not nameservers:
                # Create Cloudflare DNS zone to get nameservers (standalone mode like bot)
                from services.cloudflare import CloudflareService
                from database import save_cloudflare_zone
                
                cf_service = CloudflareService()
                zone_result = await cf_service.create_zone(request.domain_name, standalone=True)
                
                if zone_result and zone_result.get('success'):
                    zone_data = zone_result.get('result', {})
                    nameservers = zone_data.get('name_servers', [])
                    cloudflare_zone_id = zone_data.get('id')
                    
                    # Save Cloudflare zone to database (like bot does)
                    await save_cloudflare_zone(
                        domain_name=request.domain_name,
                        cf_zone_id=cloudflare_zone_id,
                        nameservers=nameservers
                    )
                    
                    logger.info(f"✅ Created Cloudflare zone {cloudflare_zone_id} with nameservers: {nameservers}")
                else:
                    error_msg = zone_result.get('errors', [{}])[0].get('message', 'Unknown error') if zone_result else 'Zone creation failed'
                    logger.error(f"❌ Failed to create Cloudflare zone for {request.domain_name}: {error_msg}")
                    return {
                        'success': False,
                        'error': f'Failed to create DNS zone: {error_msg}'
                    }
            
            # Step 3: Call OpenProvider register_domain with all parameters
            # For user contacts, pass the contact handles via tld_additional_params
            tld_params = contact_data if not request.use_hostbay_contacts and contact_data else None
            
            registration_result = await self.openprovider.register_domain(
                domain_name=request.domain_name,
                contact_handle=contact_handle,
                nameservers=nameservers,
                contact_data=None,  # Not used by OpenProvider - handles passed via tld_additional_params
                tld_additional_params=tld_params,
                period=request.period,
                auto_renew=request.auto_renew,
                privacy_protection=request.privacy_protection
            )
            
            # Step 4: Save domain to database if registration was successful (like bot does)
            if registration_result and registration_result.get('success'):
                from database import execute_update
                
                provider_domain_id = registration_result.get('domain_id')
                
                if provider_domain_id:
                    # Save domain to domains table with Cloudflare zone ID, privacy data, and provider account
                    await execute_update(
                        """INSERT INTO domains 
                           (user_id, domain_name, provider_domain_id, ownership_state, status, nameservers, 
                            cloudflare_zone_id, contact_type, privacy_enabled, original_contact_data, provider_account_id, created_at) 
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                           ON CONFLICT (domain_name) DO UPDATE SET
                           provider_domain_id = EXCLUDED.provider_domain_id,
                           cloudflare_zone_id = EXCLUDED.cloudflare_zone_id,
                           nameservers = EXCLUDED.nameservers,
                           status = EXCLUDED.status,
                           contact_type = EXCLUDED.contact_type,
                           privacy_enabled = EXCLUDED.privacy_enabled,
                           original_contact_data = EXCLUDED.original_contact_data,
                           provider_account_id = EXCLUDED.provider_account_id""",
                        (
                            user_id,
                            request.domain_name,
                            provider_domain_id,
                            'verified',  # ownership_state
                            'active',    # status
                            nameservers,
                            cloudflare_zone_id,
                            contact_type,
                            privacy_enabled,
                            original_contact_data,
                            self.account_id  # Track which OpenProvider account registered this domain
                        )
                    )
                    privacy_status = "with privacy protection" if privacy_enabled else "without privacy"
                    logger.info(f"✅ Domain saved to database: {request.domain_name} (ID: {provider_domain_id}, type: {contact_type}, {privacy_status}, account: {self.account_id})")
                else:
                    logger.warning(f"⚠️ Could not save domain to database - missing provider_domain_id or user_id")
            
            return registration_result
            
        except Exception as e:
            logger.error(f"❌ Domain registration coordinator error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _get_hostbay_contact_handle(self, domain_name: str) -> Optional[str]:
        """
        Get HostBay's shared contact handle (like bot does).
        
        This reuses the same logic as the Telegram bot for consistent contact handling.
        For TLD-specific domains, the register_domain method will handle special contacts internally.
        """
        try:
            # For all domains (including TLD-specific), get or create shared HostBay contact
            # The register_domain method will use TLD-specific contacts internally if needed
            contact_handle = await self.openprovider.get_or_create_contact_handle()
            
            if contact_handle:
                logger.info(f"✅ Using HostBay shared contact handle: {contact_handle}")
            else:
                logger.error(f"❌ Failed to get HostBay contact handle")
            
            return contact_handle
            
        except Exception as e:
            logger.error(f"❌ Error getting HostBay contact handle: {e}")
            return None
    
    async def _create_user_contact_handles(
        self, 
        contacts: Optional[Dict[str, ContactInfo]]
    ) -> Optional[Dict[str, str]]:
        """
        Create contact handles for all provided contact roles.
        
        Args:
            contacts: Dict with registrant, admin, tech, billing contacts
            
        Returns:
            Dict with contact handles for each role
        """
        try:
            if not contacts or 'registrant' not in contacts:
                logger.error("❌ No registrant contact provided")
                return None
            
            contact_handles = {}
            
            # Create handle for each contact role
            for role in ['registrant', 'admin', 'tech', 'billing']:
                if role in contacts:
                    contact_info = contacts[role]
                    
                    # Convert ContactInfo model to OpenProvider contact dict
                    contact_dict = {
                        'first_name': contact_info.first_name,
                        'last_name': contact_info.last_name,
                        'email': contact_info.email,
                        'phone': contact_info.phone,
                        'address': contact_info.address,
                        'city': contact_info.city,
                        'state': contact_info.state or '',
                        'postal_code': contact_info.postal_code,
                        'country': contact_info.country,
                        'organization': contact_info.company or ''
                    }
                    
                    # Create contact handle via OpenProvider
                    handle = await self.openprovider.create_contact_handle(contact_dict)
                    
                    if handle:
                        contact_handles[role] = handle
                        logger.info(f"✅ Created {role} contact handle: {handle}")
                    else:
                        logger.error(f"❌ Failed to create {role} contact handle")
            
            return contact_handles if contact_handles else None
            
        except Exception as e:
            logger.error(f"❌ Error creating user contact handles: {e}")
            return None
    
    def _convert_contacts_to_openprovider_format(
        self, 
        contacts: Optional[Dict[str, ContactInfo]]
    ) -> Dict[str, Dict[str, str]]:
        """
        Convert ContactInfo models to OpenProvider contact format.
        
        Args:
            contacts: Dict with registrant, admin, tech, billing contacts
            
        Returns:
            Dict with contact data in OpenProvider format
        """
        if not contacts:
            return {}
        
        openprovider_contacts = {}
        
        # Map each contact role to OpenProvider format
        for role in ['registrant', 'admin', 'tech', 'billing']:
            if role in contacts:
                contact = contacts[role]
                openprovider_contacts[role] = {
                    'first_name': contact.first_name,
                    'last_name': contact.last_name,
                    'email': contact.email,
                    'phone': contact.phone,
                    'address': contact.address,
                    'city': contact.city,
                    'state': contact.state or '',
                    'postal_code': contact.postal_code,
                    'country': contact.country,
                    'organization': contact.company or ''
                }
        
        return openprovider_contacts
