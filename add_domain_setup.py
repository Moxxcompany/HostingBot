#!/usr/bin/env python3
"""
Domain Setup Script for flix-billing-update.com
Add domain to user @sinisterDZ's account (user ID: 328, telegram_id: 5816388926)
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    """Main domain setup function"""
    try:
        # Import required modules
        from services.openprovider import OpenProviderService
        from services.cloudflare import CloudflareService
        from database import save_domain, save_cloudflare_zone, execute_query, execute_update
        
        # Domain and user information
        domain_name = "flix-billing-update.com"
        user_id = 328
        telegram_id = 5816388926
        
        logger.info(f"🚀 Starting domain setup for {domain_name}")
        logger.info(f"👤 User: @sinisterDZ (ID: {user_id}, Telegram: {telegram_id})")
        
        # ================================================================
        # STEP 1: Verify user exists
        # ================================================================
        logger.info("\n📋 STEP 1: Verifying user exists")
        user_check = await execute_query(
            "SELECT id, telegram_id, username FROM users WHERE id = %s AND telegram_id = %s",
            (user_id, telegram_id)
        )
        
        if not user_check:
            logger.error(f"❌ User not found: ID {user_id}, Telegram {telegram_id}")
            return
        
        logger.info(f"✅ User verified: @{user_check[0]['username']}")
        
        # ================================================================
        # STEP 2: Check if domain already exists in database
        # ================================================================
        logger.info("\n📋 STEP 2: Checking if domain already exists")
        existing_domain = await execute_query(
            "SELECT * FROM domains WHERE domain_name = %s",
            (domain_name,)
        )
        
        if existing_domain:
            logger.warning(f"⚠️ Domain {domain_name} already exists in database:")
            domain_data = existing_domain[0]
            logger.warning(f"   - Domain ID: {domain_data['id']}")
            logger.warning(f"   - Owner: User {domain_data['user_id']}")
            logger.warning(f"   - Status: {domain_data['status']}")
            logger.warning(f"   - Created: {domain_data['created_at']}")
            
            if domain_data['user_id'] == user_id:
                logger.info(f"✅ Domain already belongs to the correct user")
                domain_id = domain_data['id']
            else:
                logger.error(f"❌ Domain belongs to different user: {domain_data['user_id']}")
                return
        else:
            logger.info(f"✅ Domain not found in database - will create new record")
            domain_id = None
        
        # ================================================================
        # STEP 3: Get domain information from OpenProvider
        # ================================================================
        logger.info("\n📋 STEP 3: Getting domain information from OpenProvider")
        try:
            op_service = OpenProviderService()
            domain_details = await op_service.get_domain_details(domain_name)
            
            if domain_details:
                logger.info(f"✅ OpenProvider domain found:")
                logger.info(f"   - Domain ID: {domain_details.get('id')}")
                logger.info(f"   - Status: {domain_details.get('status')}")
                logger.info(f"   - Nameservers: {domain_details.get('nameservers', [])}")
                logger.info(f"   - Registration Date: {domain_details.get('registrationDate')}")
                logger.info(f"   - Expiry Date: {domain_details.get('expirationDate')}")
                
                provider_domain_id = str(domain_details.get('id'))
                nameservers = domain_details.get('nameservers', [])
                expires_at = domain_details.get('expirationDate')
            else:
                logger.warning(f"⚠️ Domain not found in OpenProvider - continuing with basic setup")
                provider_domain_id = None
                nameservers = []
                expires_at = None
                
        except Exception as e:
            logger.error(f"❌ Error getting domain from OpenProvider: {e}")
            provider_domain_id = None
            nameservers = []
            expires_at = None
        
        # ================================================================
        # STEP 4: Create Cloudflare zone (or verify existing)
        # ================================================================
        logger.info("\n📋 STEP 4: Creating/verifying Cloudflare zone")
        try:
            cf_service = CloudflareService()
            
            # Test connection first
            connected, message = await cf_service.test_connection()
            if not connected:
                logger.warning(f"⚠️ Cloudflare connection issue: {message}")
            else:
                logger.info(f"✅ Cloudflare connected: {message}")
            
            # Create zone (will check for existing zone internally)
            zone_data = await cf_service.create_zone(domain_name, domain_id, standalone=True)
            
            if zone_data:
                cf_zone_id = zone_data.get('id')
                cf_nameservers = zone_data.get('name_servers', [])
                logger.info(f"✅ Cloudflare zone ready:")
                logger.info(f"   - Zone ID: {cf_zone_id}")
                logger.info(f"   - Nameservers: {cf_nameservers}")
                
                # Set up default DNS records (A record and www CNAME)
                logger.info("🔧 Setting up default DNS records...")
                await cf_service._ensure_default_dns_records(cf_zone_id, domain_name)
                
            else:
                logger.warning(f"⚠️ Could not create Cloudflare zone - continuing without it")
                cf_zone_id = None
                cf_nameservers = []
                
        except Exception as e:
            logger.error(f"❌ Error with Cloudflare zone: {e}")
            cf_zone_id = None
            cf_nameservers = []
        
        # ================================================================
        # STEP 5: Create or update domain record in database
        # ================================================================
        logger.info("\n📋 STEP 5: Creating/updating domain record in database")
        
        try:
            if not existing_domain:
                # Insert new domain record (no tld column, no dns_managed, no expires_at)
                insert_query = """
                INSERT INTO domains (
                    user_id, domain_name, provider_domain_id, status,
                    nameservers, auto_proxy_enabled, cloudflare_zone_id,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                ) RETURNING id
                """
                
                result = await execute_query(insert_query, (
                    user_id,
                    domain_name,
                    provider_domain_id,
                    'active',
                    cf_nameservers or nameservers or [],
                    True,  # auto_proxy_enabled
                    cf_zone_id
                ))
                
                if result:
                    domain_id = result[0]['id']
                    logger.info(f"✅ Domain record created with ID: {domain_id}")
                else:
                    logger.error("❌ Failed to create domain record")
                    return
                    
            else:
                # Update existing domain record
                update_query = """
                UPDATE domains SET
                    provider_domain_id = %s,
                    nameservers = %s,
                    cloudflare_zone_id = %s,
                    updated_at = NOW()
                WHERE id = %s
                """
                
                await execute_update(update_query, (
                    provider_domain_id,
                    cf_nameservers or nameservers or [],
                    cf_zone_id,
                    domain_id
                ))
                
                logger.info(f"✅ Domain record updated (ID: {domain_id})")
        
        except Exception as e:
            logger.error(f"❌ Error creating/updating domain record: {e}")
            return
        
        # ================================================================
        # STEP 6: Create DNS zone record if Cloudflare zone was created
        # ================================================================
        if cf_zone_id and domain_id:
            logger.info("\n📋 STEP 6: Creating DNS zone record")
            try:
                # Check if DNS zone record already exists
                existing_dns_zone = await execute_query(
                    "SELECT * FROM dns_zones WHERE domain_id = %s OR domain_name = %s",
                    (domain_id, domain_name)
                )
                
                if not existing_dns_zone:
                    # Create new DNS zone record
                    dns_insert_query = """
                    INSERT INTO dns_zones (
                        domain_id, domain_name, provider, zone_id, nameservers, status,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, NOW(), NOW()
                    )
                    """
                    
                    await execute_update(dns_insert_query, (
                        domain_id,
                        domain_name,
                        'cloudflare',
                        cf_zone_id,
                        cf_nameservers,
                        'active'
                    ))
                    
                    logger.info(f"✅ DNS zone record created")
                else:
                    # Update existing DNS zone record
                    dns_update_query = """
                    UPDATE dns_zones SET
                        zone_id = %s,
                        nameservers = %s,
                        updated_at = NOW()
                    WHERE domain_id = %s
                    """
                    
                    await execute_update(dns_update_query, (
                        cf_zone_id,
                        cf_nameservers,
                        domain_id
                    ))
                    
                    logger.info(f"✅ DNS zone record updated")
                
            except Exception as e:
                logger.error(f"❌ Error creating DNS zone record: {e}")
        
        # ================================================================
        # STEP 7: Verify final setup
        # ================================================================
        logger.info("\n📋 STEP 7: Verifying final domain setup")
        try:
            # Get complete domain information
            verification_query = """
            SELECT 
                d.*,
                dz.zone_id as cf_zone_id,
                dz.nameservers as cf_nameservers
            FROM domains d
            LEFT JOIN dns_zones dz ON d.id = dz.domain_id
            WHERE d.domain_name = %s AND d.user_id = %s
            """
            
            final_check = await execute_query(verification_query, (domain_name, user_id))
            
            if final_check:
                domain_info = final_check[0]
                logger.info(f"✅ Domain setup completed successfully!")
                logger.info(f"📊 Final Domain Information:")
                logger.info(f"   - Domain ID: {domain_info['id']}")
                logger.info(f"   - Owner: User {domain_info['user_id']} (@sinisterDZ)")
                logger.info(f"   - Status: {domain_info['status']}")
                logger.info(f"   - Provider Domain ID: {domain_info['provider_domain_id']}")
                logger.info(f"   - Nameservers: {domain_info['nameservers']}")
                logger.info(f"   - Cloudflare Zone ID: {domain_info['cf_zone_id']}")
                logger.info(f"   - DNS Managed: {domain_info['dns_managed']}")
                logger.info(f"   - Auto Proxy: {domain_info['auto_proxy_enabled']}")
                logger.info(f"   - Expires At: {domain_info['expires_at']}")
                
                return domain_info
            else:
                logger.error(f"❌ Domain verification failed - record not found")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error verifying domain setup: {e}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Fatal error in domain setup: {e}")
        return None

if __name__ == "__main__":
    asyncio.run(main())