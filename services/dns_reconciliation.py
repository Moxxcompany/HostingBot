"""
DNS Reconciliation Service
Keeps the database in sync with Cloudflare by detecting and cleaning up orphaned records.

This service handles the case where DNS records are deleted directly from Cloudflare
(outside of the bot/API), ensuring the database stays consistent.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class DNSReconciliationService:
    """
    Service for reconciling DNS records between database and Cloudflare.
    
    Key features:
    - Detects orphaned database records (records deleted from Cloudflare externally)
    - Cleans up stale database entries
    - Optionally syncs new Cloudflare records to database
    - Provides detailed reconciliation reports
    """
    
    def __init__(self):
        self._running = False
        self._last_run: Optional[datetime] = None
        self._stats = {
            'total_runs': 0,
            'total_orphans_cleaned': 0,
            'total_records_synced': 0,
            'last_error': None
        }
    
    async def reconcile_domain(self, domain_name: str, zone_id: str) -> Dict:
        """
        Reconcile DNS records for a single domain.
        
        Args:
            domain_name: The domain name to reconcile
            zone_id: The Cloudflare zone ID for the domain
            
        Returns:
            Dict with reconciliation results:
            - orphans_deleted: Number of orphaned DB records deleted
            - records_synced: Number of new CF records synced to DB
            - errors: List of any errors encountered
        """
        from services.cloudflare import cloudflare
        from database import execute_query, delete_single_dns_record_from_db, update_single_dns_record_in_db
        
        result = {
            'domain': domain_name,
            'orphans_deleted': 0,
            'records_synced': 0,
            'errors': [],
            'zone_valid': True
        }
        
        try:
            cf_records = await cloudflare.list_dns_records(zone_id)
            
            if cf_records is None:
                result['zone_valid'] = False
                result['errors'].append(f"Zone {zone_id} may be deleted or inaccessible")
                await self._cleanup_all_domain_records(domain_name)
                db_records = await execute_query(
                    "SELECT cloudflare_record_id FROM dns_records WHERE domain_name = %s",
                    (domain_name,)
                )
                result['orphans_deleted'] = len(db_records) if db_records else 0
                return result
            
            cf_record_ids = set()
            for r in cf_records:
                cf_id = r.get('id')
                if cf_id:
                    cf_record_ids.add(cf_id)
            
            db_records = await execute_query(
                "SELECT id, cloudflare_record_id, record_type, name FROM dns_records WHERE domain_name = %s",
                (domain_name,)
            )
            
            if db_records:
                for db_record in db_records:
                    cf_id = db_record.get('cloudflare_record_id')
                    if cf_id and cf_id not in cf_record_ids:
                        success = await delete_single_dns_record_from_db(cf_id)
                        if success:
                            result['orphans_deleted'] += 1
                            logger.info(f"🗑️ Cleaned orphan: {db_record.get('record_type')} {db_record.get('name')} from {domain_name}")
                        else:
                            result['errors'].append(f"Failed to delete orphan record {cf_id}")
            
            db_record_ids = set()
            if db_records:
                for r in db_records:
                    rid = r.get('cloudflare_record_id')
                    if rid:
                        db_record_ids.add(rid)
            
            for cf_record in cf_records:
                cf_id = cf_record.get('id')
                if cf_id and cf_id not in db_record_ids:
                    success = await update_single_dns_record_in_db(domain_name, cf_record)
                    if success:
                        result['records_synced'] += 1
                        logger.info(f"📥 Synced from CF: {cf_record.get('type')} {cf_record.get('name')} to {domain_name}")
                    else:
                        result['errors'].append(f"Failed to sync record {cf_id}")
                        
        except Exception as e:
            error_msg = str(e)
            result['errors'].append(error_msg)
            logger.error(f"❌ Error reconciling {domain_name}: {e}")
            
            if "1001" in error_msg or "Invalid zone" in error_msg:
                result['zone_valid'] = False
                await self._cleanup_all_domain_records(domain_name)
        
        return result
    
    async def _cleanup_all_domain_records(self, domain_name: str) -> int:
        """Clean up all DNS records for a domain with an invalid/deleted zone"""
        from database import execute_update
        
        try:
            rows_deleted = await execute_update(
                "DELETE FROM dns_records WHERE domain_name = %s",
                (domain_name,)
            )
            if rows_deleted and rows_deleted > 0:
                logger.info(f"🧹 Cleaned up {rows_deleted} orphaned records for {domain_name} (zone deleted)")
            return rows_deleted or 0
        except Exception as e:
            logger.error(f"Failed to cleanup records for {domain_name}: {e}")
            return 0
    
    async def reconcile_all_domains(self, notify_admin: bool = False) -> Dict:
        """
        Reconcile DNS records for all domains in the system.
        
        Args:
            notify_admin: Whether to send admin notification with results
            
        Returns:
            Summary of reconciliation across all domains
        """
        from database import execute_query
        
        self._running = True
        start_time = datetime.utcnow()
        
        summary = {
            'started_at': start_time.isoformat(),
            'domains_processed': 0,
            'total_orphans_deleted': 0,
            'total_records_synced': 0,
            'invalid_zones': 0,
            'errors': [],
            'domain_results': []
        }
        
        try:
            domains = await execute_query(
                "SELECT domain_name, cloudflare_zone_id FROM domains WHERE cloudflare_zone_id IS NOT NULL"
            )
            
            if not domains:
                logger.info("📭 No domains with Cloudflare zones found for reconciliation")
                summary['completed_at'] = datetime.utcnow().isoformat()
                return summary
            
            logger.info(f"🔄 Starting DNS reconciliation for {len(domains)} domains...")
            
            for domain in domains:
                domain_name = domain.get('domain_name')
                zone_id = domain.get('cloudflare_zone_id')
                
                if not domain_name or not zone_id:
                    continue
                
                result = await self.reconcile_domain(domain_name, zone_id)
                summary['domains_processed'] += 1
                summary['total_orphans_deleted'] += result['orphans_deleted']
                summary['total_records_synced'] += result['records_synced']
                
                if not result['zone_valid']:
                    summary['invalid_zones'] += 1
                
                if result['errors']:
                    summary['errors'].extend(result['errors'])
                
                if result['orphans_deleted'] > 0 or result['records_synced'] > 0 or result['errors']:
                    summary['domain_results'].append(result)
                
                await asyncio.sleep(0.1)
            
            summary['completed_at'] = datetime.utcnow().isoformat()
            duration = (datetime.utcnow() - start_time).total_seconds()
            summary['duration_seconds'] = duration
            
            self._stats['total_runs'] += 1
            self._stats['total_orphans_cleaned'] += summary['total_orphans_deleted']
            self._stats['total_records_synced'] += summary['total_records_synced']
            self._last_run = datetime.utcnow()
            
            logger.info(f"✅ DNS Reconciliation complete: {summary['domains_processed']} domains, "
                       f"{summary['total_orphans_deleted']} orphans cleaned, "
                       f"{summary['total_records_synced']} records synced "
                       f"({duration:.1f}s)")
            
            if notify_admin and (summary['total_orphans_deleted'] > 0 or summary['invalid_zones'] > 0):
                await self._notify_admin(summary)
                
        except Exception as e:
            summary['errors'].append(str(e))
            self._stats['last_error'] = str(e)
            logger.error(f"❌ DNS Reconciliation failed: {e}")
        finally:
            self._running = False
        
        return summary
    
    async def reconcile_user_domains(self, user_id: int) -> Dict:
        """Reconcile DNS records for a specific user's domains"""
        from database import execute_query
        
        summary = {
            'user_id': user_id,
            'domains_processed': 0,
            'total_orphans_deleted': 0,
            'total_records_synced': 0,
            'results': []
        }
        
        try:
            domains = await execute_query(
                """SELECT d.domain_name, d.cloudflare_zone_id 
                   FROM domains d 
                   WHERE d.user_id = %s AND d.cloudflare_zone_id IS NOT NULL""",
                (user_id,)
            )
            
            if not domains:
                return summary
            
            for domain in domains:
                result = await self.reconcile_domain(
                    domain.get('domain_name'),
                    domain.get('cloudflare_zone_id')
                )
                summary['domains_processed'] += 1
                summary['total_orphans_deleted'] += result['orphans_deleted']
                summary['total_records_synced'] += result['records_synced']
                summary['results'].append(result)
                
        except Exception as e:
            logger.error(f"Failed to reconcile user {user_id} domains: {e}")
            summary['error'] = str(e)
        
        return summary
    
    async def _notify_admin(self, summary: Dict):
        """Log admin notification about reconciliation results"""
        try:
            message = (
                f"🔄 DNS Reconciliation Report - "
                f"Domains: {summary['domains_processed']}, "
                f"Orphans cleaned: {summary['total_orphans_deleted']}, "
                f"Records synced: {summary['total_records_synced']}, "
                f"Invalid zones: {summary['invalid_zones']}, "
                f"Duration: {summary.get('duration_seconds', 0):.1f}s"
            )
            
            if summary['errors']:
                message += f", Errors: {len(summary['errors'])}"
            
            logger.info(f"📬 {message}")
            
        except Exception as e:
            logger.error(f"Failed to log admin notification: {e}")
    
    def get_stats(self) -> Dict:
        """Get reconciliation service statistics"""
        return {
            **self._stats,
            'is_running': self._running,
            'last_run': self._last_run.isoformat() if self._last_run else None
        }


dns_reconciliation = DNSReconciliationService()


async def run_dns_reconciliation():
    """Entry point for scheduled reconciliation job"""
    logger.info("📅 Scheduled DNS reconciliation starting...")
    result = await dns_reconciliation.reconcile_all_domains(notify_admin=True)
    return result
