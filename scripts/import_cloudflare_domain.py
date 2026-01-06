#!/usr/bin/env python3
"""
Import a domain from Cloudflare into the bot's database.
This script fetches a domain's zone from Cloudflare and creates all necessary database entries.

Usage:
    python scripts/import_cloudflare_domain.py <domain_name> <user_id>
    
Example:
    python scripts/import_cloudflare_domain.py ledgerlive-activation.com 497
"""

import asyncio
import sys
import os
import logging

# Add parent directory to path to import project modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.cloudflare import CloudflareService
from database import (
    save_cloudflare_zone,
    save_dns_records_to_db,
    execute_query,
    execute_update
)

# Initialize logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def find_cloudflare_zone(domain_name: str):
    """Find a domain's zone in Cloudflare by searching all zones"""
    logger.info(f"🔍 Searching for {domain_name} in Cloudflare...")
    
    try:
        cloudflare = CloudflareService()
        
        # Get all zones from Cloudflare
        client = await cloudflare.get_client()
        
        # Build auth headers
        if cloudflare.email and cloudflare.api_key:
            headers = {
                'X-Auth-Email': cloudflare.email,
                'X-Auth-Key': cloudflare.api_key
            }
        else:
            logger.error("❌ Cloudflare credentials not configured")
            return None
        
        # Search for zone
        response = await client.get(
            f"{cloudflare.base_url}/zones",
            headers=headers,
            params={'name': domain_name}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                zones = data.get('result', [])
                if zones:
                    zone = zones[0]
                    logger.info(f"✅ Found zone in Cloudflare:")
                    logger.info(f"   Zone ID: {zone['id']}")
                    logger.info(f"   Status: {zone['status']}")
                    logger.info(f"   Nameservers: {zone.get('name_servers', [])}")
                    return zone
                else:
                    logger.error(f"❌ Zone not found for {domain_name} in Cloudflare")
                    return None
            else:
                errors = data.get('errors', [])
                logger.error(f"❌ Cloudflare API errors: {errors}")
                return None
        else:
            logger.error(f"❌ Cloudflare API request failed: HTTP {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error searching Cloudflare: {e}")
        import traceback
        traceback.print_exc()
        return None


async def import_domain_to_database(domain_name: str, user_id: int, zone_data: dict):
    """Import domain and its DNS records into the database"""
    logger.info(f"💾 Importing {domain_name} to database...")
    
    try:
        zone_id = zone_data['id']
        nameservers = zone_data.get('name_servers', [])
        status = zone_data.get('status', 'active')
        
        # Step 1: Check if user exists
        logger.info(f"🔍 Checking if user {user_id} exists...")
        user_check = await execute_query(
            "SELECT id, telegram_id FROM users WHERE id = %s",
            (user_id,)
        )
        
        if not user_check:
            logger.error(f"❌ User ID {user_id} not found in database")
            logger.error(f"   Please provide a valid user ID from the users table")
            return False
        
        logger.info(f"✅ User found: {user_check[0]['telegram_id']}")
        
        # Step 2: Create domain entry
        logger.info(f"💾 Creating domain entry...")
        await execute_update(
            """INSERT INTO domains (user_id, domain_name, status, expires_at)
               VALUES (%s, %s, %s, NOW() + INTERVAL '1 year')
               ON CONFLICT (domain_name) DO NOTHING""",
            (user_id, domain_name, 'active')
        )
        logger.info(f"✅ Domain entry created")
        
        # Step 3: Save Cloudflare zone
        logger.info(f"💾 Saving Cloudflare zone...")
        await save_cloudflare_zone(domain_name, zone_id, nameservers, status)
        logger.info(f"✅ Cloudflare zone saved")
        
        # Step 4: Fetch and save DNS records
        logger.info(f"🌐 Fetching DNS records from Cloudflare...")
        cloudflare = CloudflareService()
        dns_records = await cloudflare.list_dns_records(zone_id)
        
        if dns_records:
            logger.info(f"✅ Found {len(dns_records)} DNS records")
            
            # Record types summary
            record_types = {}
            for record in dns_records:
                rtype = record.get('type', 'UNKNOWN')
                record_types[rtype] = record_types.get(rtype, 0) + 1
            
            logger.info(f"📊 Record types:")
            for rtype, count in sorted(record_types.items()):
                logger.info(f"   • {rtype}: {count}")
            
            # Save to database
            logger.info(f"💾 Saving DNS records to database...")
            await save_dns_records_to_db(domain_name, dns_records)
            logger.info(f"✅ DNS records saved")
        else:
            logger.warning(f"⚠️ No DNS records found in Cloudflare")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error importing domain: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main entry point"""
    if len(sys.argv) < 3:
        print("❌ Error: Domain name and user ID required")
        print("\nUsage: python scripts/import_cloudflare_domain.py <domain_name> <user_id>")
        print("Example: python scripts/import_cloudflare_domain.py ledgerlive-activation.com 497")
        print("\nTo find user ID, run:")
        print("  SELECT id, telegram_id FROM users WHERE telegram_id = <telegram_user_id>;")
        sys.exit(1)
    
    domain_name = sys.argv[1].strip().lower()
    
    try:
        user_id = int(sys.argv[2])
    except ValueError:
        print("❌ Error: User ID must be a number")
        sys.exit(1)
    
    logger.info(f"🚀 Cloudflare Domain Import Tool")
    logger.info(f"=" * 60)
    logger.info(f"Domain: {domain_name}")
    logger.info(f"User ID: {user_id}")
    logger.info(f"=" * 60)
    
    # Step 1: Find zone in Cloudflare
    zone_data = await find_cloudflare_zone(domain_name)
    
    if not zone_data:
        logger.error(f"")
        logger.error(f"❌ IMPORT FAILED")
        logger.error(f"   Domain not found in Cloudflare")
        logger.error(f"   Please ensure the domain is added to your Cloudflare account")
        sys.exit(1)
    
    # Step 2: Import to database
    success = await import_domain_to_database(domain_name, user_id, zone_data)
    
    if success:
        logger.info(f"")
        logger.info(f"✅ IMPORT COMPLETE")
        logger.info(f"   Domain: {domain_name}")
        logger.info(f"   User ID: {user_id}")
        logger.info(f"   Zone ID: {zone_data['id']}")
        logger.info(f"")
        logger.info(f"   The domain is now visible in the user's bot interface")
        logger.info(f"   All DNS records have been synced")
        sys.exit(0)
    else:
        logger.error(f"")
        logger.error(f"❌ IMPORT FAILED")
        logger.error(f"   Please check the errors above")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
