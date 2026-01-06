#!/usr/bin/env python3
"""
One-time migration script to backfill missing Cloudflare and OpenProvider data for existing domains.

This script will:
1. Find all domains missing nameservers, cloudflare_zone_id, or OpenProvider data
2. Query Cloudflare API to retrieve zone information for each domain
3. Query OpenProvider API to retrieve domain registration details
4. Update the database with the retrieved information
5. Create basic DNS records if they don't exist

Safe to run multiple times (idempotent).
Run once on deployment after the new schema changes.
"""

import asyncio
import logging
import os
import sys
from typing import List, Dict, Optional, Any

# Add the parent directory to the Python path to import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our application modules
from database import init_database, execute_query, execute_update
from services.cloudflare import CloudflareService
from services.openprovider import OpenProviderService

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DomainMigration:
    def __init__(self):
        self.cloudflare = CloudflareService()
        self.openprovider = OpenProviderService()
        self.processed_count = 0
        self.updated_count = 0
        self.error_count = 0
        self.cloudflare_updated = 0
        self.openprovider_updated = 0
        
    async def run_migration(self):
        """Main migration entry point."""
        logger.info("🚀 Starting domain Cloudflare data backfill migration...")
        
        try:
            # Initialize database
            await init_database()
            
            # Create unique constraint if missing
            await self._create_unique_constraint_if_missing()
            
            # Find domains missing Cloudflare or OpenProvider data
            domains_to_process = await self._find_domains_missing_data()
            
            if not domains_to_process:
                logger.info("✅ No domains require data backfill - migration complete")
                return
                
            logger.info(f"📊 Found {len(domains_to_process)} domains requiring data backfill")
            
            # Process each domain
            for domain in domains_to_process:
                await self._process_domain(domain)
                
            # Summary report
            logger.info(f"🎉 Migration completed!")
            logger.info(f"   📈 Domains processed: {self.processed_count}")
            logger.info(f"   ✅ Total domains updated: {self.updated_count}")
            logger.info(f"   🌐 Cloudflare data updated: {self.cloudflare_updated}")
            logger.info(f"   🏢 OpenProvider data updated: {self.openprovider_updated}")
            logger.info(f"   ❌ Domains with errors: {self.error_count}")
            
        except Exception as e:
            logger.error(f"❌ Migration failed with error: {e}")
            raise
            
    async def _find_domains_missing_data(self) -> List[Dict]:
        """Find all domains that are missing nameservers, cloudflare_zone_id, or OpenProvider data."""
        logger.info("🔍 Searching for domains missing Cloudflare or OpenProvider data...")
        
        domains = await execute_query("""
            SELECT 
                domain_name, 
                nameservers, 
                cloudflare_zone_id, 
                status,
                provider_domain_id,
                user_id,
                created_at
            FROM domains 
            WHERE 
                status = 'active' 
                AND (
                    nameservers IS NULL 
                    OR array_length(nameservers, 1) IS NULL 
                    OR cloudflare_zone_id IS NULL 
                    OR cloudflare_zone_id = ''
                    OR provider_domain_id IS NULL
                    OR provider_domain_id = ''
                )
            ORDER BY created_at ASC
        """)
        
        logger.info(f"📋 Found {len(domains)} domains missing data")
        
        for domain in domains:
            missing_items = []
            if not domain.get('nameservers') or not domain['nameservers']:
                missing_items.append("nameservers")
            if not domain.get('cloudflare_zone_id'):
                missing_items.append("cloudflare_zone_id")
            if not domain.get('provider_domain_id'):
                missing_items.append("provider_domain_id")
                
            logger.info(f"   🌐 {domain['domain_name']} - missing: {', '.join(missing_items)}")
            
        return domains
        
    async def _process_domain(self, domain: Dict):
        """Process a single domain to backfill missing Cloudflare and OpenProvider data."""
        domain_name = domain['domain_name']
        logger.info(f"🔄 Processing domain: {domain_name}")
        
        try:
            self.processed_count += 1
            domain_updated = False
            
            # Process Cloudflare data if missing
            missing_cloudflare = (
                not domain.get('nameservers') or 
                not domain['nameservers'] or 
                not domain.get('cloudflare_zone_id')
            )
            
            if missing_cloudflare:
                cloudflare_success = await self._process_cloudflare_data(domain_name)
                if cloudflare_success:
                    self.cloudflare_updated += 1
                    domain_updated = True
            
            # Process OpenProvider data if missing
            missing_openprovider = not domain.get('provider_domain_id')
            
            if missing_openprovider:
                openprovider_success = await self._process_openprovider_data(domain_name)
                if openprovider_success:
                    self.openprovider_updated += 1
                    domain_updated = True
            
            if domain_updated:
                self.updated_count += 1
                logger.info(f"✅ Successfully updated {domain_name}")
            else:
                logger.info(f"ℹ️  No updates needed for {domain_name}")
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"❌ Error processing {domain_name}: {e}")
            
    async def _process_cloudflare_data(self, domain_name: str) -> bool:
        """Process Cloudflare data for a domain."""
        try:
            zone_info = await self._get_cloudflare_zone_info(domain_name)
            
            if not zone_info:
                logger.info(f"ℹ️  No Cloudflare zone found for {domain_name}")
                return False
                
            # Update database with Cloudflare information
            await self._update_domain_cloudflare_data(domain_name, zone_info)
            
            # Create basic DNS records if they don't exist
            await self._ensure_basic_dns_records(domain_name, zone_info)
            
            logger.info(f"✅ Updated Cloudflare data for {domain_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error processing Cloudflare data for {domain_name}: {e}")
            return False
            
    async def _process_openprovider_data(self, domain_name: str) -> bool:
        """Process OpenProvider data for a domain."""
        try:
            domain_details = await self.openprovider.get_domain_details(domain_name)
            
            if not domain_details or not domain_details.get('success'):
                logger.info(f"ℹ️  No OpenProvider domain found for {domain_name}")
                return False
                
            domain_data = domain_details.get('data', {})
            domain_id = domain_data.get('id')
            
            if not domain_id:
                logger.warning(f"⚠️  No domain ID found in OpenProvider response for {domain_name}")
                return False
                
            # Update database with OpenProvider domain ID
            await execute_update("""
                UPDATE domains 
                SET 
                    provider_domain_id = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE domain_name = %s
            """, (str(domain_id), domain_name))
            
            logger.info(f"✅ Updated OpenProvider data for {domain_name} (ID: {domain_id})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error processing OpenProvider data for {domain_name}: {e}")
            return False
            
    async def _get_cloudflare_zone_info(self, domain_name: str) -> Optional[Dict]:
        """Retrieve zone information from Cloudflare API."""
        logger.debug(f"🌐 Querying Cloudflare for zone: {domain_name}")
        
        try:
            # Use the existing Cloudflare service to get zone info
            zone_info = await self.cloudflare.get_zone_by_name(domain_name)
            
            if zone_info and zone_info.get('success'):
                zone_data = zone_info.get('result')
                if zone_data:
                    logger.info(f"✅ Found Cloudflare zone for {domain_name}: {zone_data.get('id')}")
                    return {
                        'zone_id': zone_data.get('id'),
                        'nameservers': zone_data.get('name_servers', []),
                        'status': zone_data.get('status'),
                        'zone_data': zone_data
                    }
                    
            logger.info(f"ℹ️  No active Cloudflare zone found for {domain_name}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error querying Cloudflare for {domain_name}: {e}")
            return None
            
    async def _update_domain_cloudflare_data(self, domain_name: str, zone_info: Dict):
        """Update domain table with Cloudflare zone information."""
        logger.debug(f"💾 Updating database for {domain_name}")
        
        nameservers = zone_info.get('nameservers', [])
        zone_id = zone_info.get('zone_id')
        
        if not nameservers or not zone_id:
            logger.warning(f"⚠️  Incomplete zone info for {domain_name} - nameservers: {bool(nameservers)}, zone_id: {bool(zone_id)}")
            return
            
        await execute_update("""
            UPDATE domains 
            SET 
                nameservers = %s,
                cloudflare_zone_id = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE domain_name = %s
        """, (nameservers, zone_id, domain_name))
        
        logger.info(f"📝 Updated {domain_name} with {len(nameservers)} nameservers and zone ID {zone_id}")
        
    async def _ensure_basic_dns_records(self, domain_name: str, zone_info: Dict):
        """Create basic DNS records in local database if they don't exist."""
        logger.debug(f"📝 Checking DNS records for {domain_name}")
        
        try:
            # Check if we already have DNS records for this domain
            existing_records = await execute_query("""
                SELECT COUNT(*) as record_count 
                FROM dns_records 
                WHERE domain_name = %s
            """, (domain_name,))
            
            if existing_records and existing_records[0]['record_count'] > 0:
                logger.debug(f"ℹ️  DNS records already exist for {domain_name}")
                return
                
            # Get current DNS records from Cloudflare
            zone_id = zone_info.get('zone_id')
            if not zone_id:
                return
                
            cloudflare_records = await self.cloudflare.list_dns_records(zone_id)
            
            if cloudflare_records and isinstance(cloudflare_records, dict) and cloudflare_records.get('success'):
                records = cloudflare_records.get('result', [])
                
                for record in records:
                    # Insert basic record information
                    await execute_update("""
                        INSERT INTO dns_records 
                        (domain_name, record_type, name, content, ttl, cloudflare_record_id, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (domain_name, record_type, name) DO NOTHING
                    """, (
                        domain_name,
                        record['type'],
                        record['name'],
                        record['content'],
                        record.get('ttl', 3600),
                        record['id']
                    ))
                    
                logger.info(f"📝 Created {len(records)} DNS records for {domain_name}")
                
        except Exception as e:
            logger.error(f"❌ Error creating DNS records for {domain_name}: {e}")
            
    async def _create_unique_constraint_if_missing(self):
        """Create unique constraint on dns_records if it doesn't exist."""
        try:
            await execute_update("""
                ALTER TABLE dns_records 
                ADD CONSTRAINT IF NOT EXISTS dns_records_unique 
                UNIQUE (domain_name, record_type, name)
            """)
            logger.info("✅ DNS records unique constraint verified")
        except Exception as e:
            logger.warning(f"⚠️  Could not create DNS records unique constraint: {e}")

async def main():
    """Main entry point for the migration script."""
    print("🚀 Domain Cloudflare & OpenProvider Data Backfill Migration")
    print("=" * 60)
    
    migration = DomainMigration()
    await migration.run_migration()
    
    print("=" * 60)
    print("✅ Migration completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())