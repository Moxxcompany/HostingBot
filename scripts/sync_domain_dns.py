#!/usr/bin/env python3
"""
Sync DNS records from Cloudflare to database for a specific domain.
This script fetches DNS records from Cloudflare and saves them to the local database.

Usage:
    python scripts/sync_domain_dns.py <domain_name>
    
Example:
    python scripts/sync_domain_dns.py ledgerlive-activation.com
"""

import asyncio
import sys
import os
import logging

# Add parent directory to path to import project modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.cloudflare import CloudflareService
from database import (
    get_cloudflare_zone,
    save_dns_records_to_db,
    get_dns_records_from_db
)

# Initialize logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def sync_domain_dns_records(domain_name: str):
    """
    Sync DNS records from Cloudflare to database for a specific domain.
    
    Args:
        domain_name: The domain name to sync (e.g., 'example.com')
    """
    logger.info(f"🔄 Starting DNS sync for domain: {domain_name}")
    
    try:
        # Step 1: Get Cloudflare zone info from database
        logger.info(f"📦 Checking for Cloudflare zone in database...")
        cf_zone = await get_cloudflare_zone(domain_name)
        
        if not cf_zone:
            logger.error(f"❌ No Cloudflare zone found for {domain_name}")
            logger.error(f"   This domain must be added to Cloudflare first")
            logger.error(f"   Or the cloudflare_zones table needs the zone_id")
            return False
        
        zone_id = cf_zone['cf_zone_id']
        logger.info(f"✅ Found Cloudflare zone: {zone_id}")
        
        # Step 2: Check current database records
        logger.info(f"📦 Checking current database records...")
        db_records = await get_dns_records_from_db(domain_name)
        logger.info(f"   Current database records: {len(db_records)}")
        
        # Step 3: Fetch DNS records from Cloudflare API
        logger.info(f"🌐 Fetching DNS records from Cloudflare API...")
        cloudflare = CloudflareService()
        cf_records = await cloudflare.list_dns_records(zone_id)
        
        if not cf_records:
            logger.warning(f"⚠️ No DNS records found in Cloudflare for {domain_name}")
            logger.info(f"   This might mean the zone has no records yet")
            return True
        
        logger.info(f"✅ Found {len(cf_records)} DNS records in Cloudflare")
        
        # Step 4: Display record summary
        record_types = {}
        for record in cf_records:
            rtype = record.get('type', 'UNKNOWN')
            record_types[rtype] = record_types.get(rtype, 0) + 1
        
        logger.info(f"📊 Record types found:")
        for rtype, count in sorted(record_types.items()):
            logger.info(f"   • {rtype}: {count}")
        
        # Step 5: Save all records to database
        logger.info(f"💾 Saving DNS records to database...")
        success = await save_dns_records_to_db(domain_name, cf_records)
        
        if success:
            logger.info(f"✅ DNS sync completed successfully for {domain_name}")
            logger.info(f"   Synced {len(cf_records)} records to database")
            
            # Step 6: Verify database records
            logger.info(f"🔍 Verifying database records...")
            db_records_after = await get_dns_records_from_db(domain_name)
            logger.info(f"   Database now has {len(db_records_after)} records")
            
            # Display synced records
            logger.info(f"📋 Synced DNS records:")
            for record in db_records_after[:10]:  # Show first 10
                rtype = record.get('record_type')
                name = record.get('name')
                content = record.get('content', '')[:50]  # Truncate long content
                logger.info(f"   • {rtype}: {name} → {content}")
            
            if len(db_records_after) > 10:
                logger.info(f"   ... and {len(db_records_after) - 10} more records")
            
            return True
        else:
            logger.error(f"❌ Failed to save DNS records to database")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error syncing DNS records: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("❌ Error: Domain name required")
        print("\nUsage: python scripts/sync_domain_dns.py <domain_name>")
        print("Example: python scripts/sync_domain_dns.py ledgerlive-activation.com")
        sys.exit(1)
    
    domain_name = sys.argv[1].strip().lower()
    
    logger.info(f"🚀 DNS Record Sync Tool")
    logger.info(f"=" * 60)
    logger.info(f"Domain: {domain_name}")
    logger.info(f"=" * 60)
    
    # Run sync (connection pool initialized automatically)
    success = await sync_domain_dns_records(domain_name)
    
    if success:
        logger.info(f"")
        logger.info(f"✅ SYNC COMPLETE")
        logger.info(f"   DNS records for {domain_name} are now visible in the bot")
        logger.info(f"   Users can view them in the DNS dashboard")
        sys.exit(0)
    else:
        logger.error(f"")
        logger.error(f"❌ SYNC FAILED")
        logger.error(f"   Please check the errors above")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
