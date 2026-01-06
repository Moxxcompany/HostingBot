#!/usr/bin/env python3
"""
Bulk DNS Sync Orchestrator
Syncs DNS records from Cloudflare to database for multiple domains

This script:
- Fetches all domains with Cloudflare zones but missing DNS records
- Syncs them in batches with rate limiting
- Handles errors gracefully with retry logic
- Provides detailed progress logging

Usage:
    python scripts/bulk_sync_dns.py [--pilot] [--limit N]
    
Options:
    --pilot     Test mode: only sync 3 low-risk domains
    --limit N   Limit sync to first N domains
    --dry-run   Show what would be synced without actually syncing
"""

import asyncio
import sys
import os
import logging
import argparse
import time
from typing import List, Dict, Tuple
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import execute_query, get_dns_records_from_db
from services.cloudflare import CloudflareService
from scripts.sync_domain_dns import sync_domain_dns_records

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BulkDNSSync:
    """Orchestrates bulk DNS synchronization with rate limiting and error handling"""
    
    def __init__(self, pilot_mode=False, limit=None, dry_run=False):
        self.pilot_mode = pilot_mode
        self.limit = limit
        self.dry_run = dry_run
        self.rate_limit_delay = 6  # seconds between domains (10 domains/minute)
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        
        self.success_count = 0
        self.failure_count = 0
        self.skipped_count = 0
        self.failed_domains = []
        
    async def get_domains_to_sync(self) -> List[Dict]:
        """Get list of domains that need DNS sync (have Cloudflare zones but no DNS records)"""
        logger.info("🔍 Fetching domains that need DNS sync...")
        
        query = """
            SELECT 
                cz.domain_name,
                cz.cf_zone_id,
                d.user_id,
                u.username,
                u.telegram_id,
                COALESCE(COUNT(dr.id), 0) as dns_records_count
            FROM cloudflare_zones cz
            INNER JOIN domains d ON cz.domain_name = d.domain_name
            INNER JOIN users u ON d.user_id = u.id
            LEFT JOIN dns_records dr ON cz.domain_name = dr.domain_name
            GROUP BY cz.domain_name, cz.cf_zone_id, d.user_id, u.username, u.telegram_id
            HAVING COUNT(dr.id) = 0
            ORDER BY cz.domain_name
        """
        
        results = await execute_query(query)
        
        if not results:
            logger.info("✅ All domains already have DNS records synced!")
            return []
        
        logger.info(f"📊 Found {len(results)} domains missing DNS records")
        
        # Apply limit if specified
        if self.pilot_mode:
            logger.info("🧪 PILOT MODE: Limiting to 3 domains for testing")
            results = results[:3]
        elif self.limit:
            logger.info(f"📏 LIMIT MODE: Limiting to {self.limit} domains")
            results = results[:self.limit]
        
        return results
    
    async def sync_single_domain_with_retry(self, domain: Dict) -> Tuple[bool, str]:
        """Sync a single domain with retry logic"""
        domain_name = domain['domain_name']
        
        for attempt in range(1, self.max_retries + 1):
            try:
                if self.dry_run:
                    logger.info(f"[DRY-RUN] Would sync: {domain_name}")
                    return True, "dry-run"
                
                logger.info(f"📡 Syncing {domain_name} (attempt {attempt}/{self.max_retries})")
                
                success = await sync_domain_dns_records(domain_name)
                
                if success:
                    logger.info(f"✅ Successfully synced {domain_name}")
                    return True, "success"
                else:
                    logger.warning(f"⚠️ Sync returned False for {domain_name}")
                    if attempt < self.max_retries:
                        logger.info(f"   Retrying in {self.retry_delay}s...")
                        await asyncio.sleep(self.retry_delay)
                    continue
                    
            except Exception as e:
                logger.error(f"❌ Error syncing {domain_name} (attempt {attempt}): {e}")
                if attempt < self.max_retries:
                    logger.info(f"   Retrying in {self.retry_delay}s...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    return False, str(e)
        
        return False, "max retries exceeded"
    
    async def run_bulk_sync(self):
        """Execute bulk DNS sync with rate limiting"""
        start_time = time.time()
        
        logger.info("=" * 80)
        logger.info("BULK DNS SYNC ORCHESTRATOR")
        logger.info("=" * 80)
        logger.info("")
        
        if self.dry_run:
            logger.info("🔍 DRY-RUN MODE: No actual changes will be made")
        if self.pilot_mode:
            logger.info("🧪 PILOT MODE: Testing on 3 domains first")
        
        # Get domains to sync
        domains = await self.get_domains_to_sync()
        
        if not domains:
            logger.info("🎉 Nothing to sync!")
            return True
        
        total_domains = len(domains)
        logger.info(f"📋 Will sync {total_domains} domains")
        logger.info(f"⏱️ Estimated time: ~{total_domains * self.rate_limit_delay / 60:.1f} minutes")
        logger.info("")
        
        # Sync each domain with rate limiting
        for idx, domain in enumerate(domains, 1):
            domain_name = domain['domain_name']
            username = domain.get('username', 'unknown')
            
            logger.info("-" * 80)
            logger.info(f"[{idx}/{total_domains}] Domain: {domain_name}")
            logger.info(f"           Owner: @{username} (user_id={domain['user_id']})")
            logger.info(f"        Zone ID: {domain['cf_zone_id']}")
            
            # Sync with retry
            success, message = await self.sync_single_domain_with_retry(domain)
            
            if success:
                self.success_count += 1
            else:
                self.failure_count += 1
                self.failed_domains.append({
                    'domain': domain_name,
                    'username': username,
                    'error': message
                })
            
            # Rate limiting (except for last domain)
            if idx < total_domains:
                logger.info(f"⏸️ Rate limiting: waiting {self.rate_limit_delay}s before next domain...")
                await asyncio.sleep(self.rate_limit_delay)
        
        # Summary
        elapsed = time.time() - start_time
        logger.info("")
        logger.info("=" * 80)
        logger.info("SYNC SUMMARY")
        logger.info("=" * 80)
        logger.info(f"✅ Successfully synced: {self.success_count}")
        logger.info(f"❌ Failed: {self.failure_count}")
        logger.info(f"📊 Total processed: {total_domains}")
        logger.info(f"⏱️ Time elapsed: {elapsed / 60:.1f} minutes")
        logger.info("")
        
        if self.failed_domains:
            logger.error("⚠️ FAILED DOMAINS:")
            for failed in self.failed_domains:
                logger.error(f"   • {failed['domain']} (@{failed['username']}): {failed['error']}")
            logger.info("")
        
        # Validation
        if not self.dry_run:
            await self.validate_sync()
        
        return self.failure_count == 0
    
    async def validate_sync(self):
        """Validate that synced domains now have DNS records"""
        logger.info("🔍 Validating sync results...")
        
        query = """
            SELECT 
                cz.domain_name,
                COUNT(dr.id) as dns_records_count
            FROM cloudflare_zones cz
            LEFT JOIN dns_records dr ON cz.domain_name = dr.domain_name
            GROUP BY cz.domain_name
            HAVING COUNT(dr.id) = 0
        """
        
        still_missing = await execute_query(query)
        
        if still_missing:
            logger.warning(f"⚠️ {len(still_missing)} domains still have no DNS records:")
            for domain in still_missing[:10]:  # Show first 10
                logger.warning(f"   • {domain['domain_name']}")
        else:
            logger.info("✅ All domains now have DNS records!")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Bulk DNS Sync Orchestrator')
    parser.add_argument('--pilot', action='store_true', help='Pilot mode: sync only 3 domains for testing')
    parser.add_argument('--limit', type=int, help='Limit sync to first N domains')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be synced without syncing')
    
    args = parser.parse_args()
    
    orchestrator = BulkDNSSync(
        pilot_mode=args.pilot,
        limit=args.limit,
        dry_run=args.dry_run
    )
    
    success = await orchestrator.run_bulk_sync()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
