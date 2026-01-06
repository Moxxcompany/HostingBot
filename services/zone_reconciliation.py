"""
Cloudflare Zone Reconciliation Service

Syncs Cloudflare zone status with the local database.
Detects zones deleted externally and cleans up orphaned references.
"""
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ZoneReconciliationService:
    """Service to reconcile Cloudflare zones between database and Cloudflare API"""
    
    def __init__(self):
        self._running = False
        self._last_run: Optional[datetime] = None
        self._stats = {
            'total_runs': 0,
            'zones_checked': 0,
            'orphaned_zones_cleaned': 0,
            'zone_status_updates': 0,
            'last_error': None
        }
    
    async def reconcile_all_zones(self, notify_admin: bool = False) -> Dict:
        """
        Reconcile all Cloudflare zones in the database.
        
        Returns:
            Summary of reconciliation results
        """
        from services.cloudflare import cloudflare
        from database import execute_query, execute_update
        
        start_time = datetime.now(timezone.utc)
        self._running = True
        
        summary = {
            'zones_checked': 0,
            'orphaned_zones_cleaned': 0,
            'zone_status_updates': 0,
            'errors': [],
            'duration_seconds': 0
        }
        
        try:
            logger.info("🔄 Starting Cloudflare zone reconciliation...")
            
            cf_zones = await cloudflare.list_zones()
            if cf_zones is None:
                summary['errors'].append("Failed to fetch zones from Cloudflare")
                logger.error("❌ Failed to fetch zones from Cloudflare API")
                return summary
            
            cf_zone_ids: Set[str] = set()
            cf_zone_data: Dict[str, Dict] = {}
            for zone in cf_zones:
                zone_id = zone.get('id')
                if zone_id:
                    cf_zone_ids.add(zone_id)
                    cf_zone_data[zone_id] = zone
            
            logger.info(f"📊 Found {len(cf_zone_ids)} zones in Cloudflare account")
            
            db_zones = await execute_query(
                """SELECT d.id, d.domain_name, d.cloudflare_zone_id, d.status 
                   FROM domains d 
                   WHERE d.cloudflare_zone_id IS NOT NULL"""
            )
            
            if not db_zones:
                logger.info("ℹ️ No domains with Cloudflare zones in database")
                return summary
            
            for db_zone in db_zones:
                summary['zones_checked'] += 1
                zone_id = db_zone.get('cloudflare_zone_id')
                domain_name = db_zone.get('domain_name')
                domain_id = db_zone.get('id')
                
                if zone_id not in cf_zone_ids:
                    logger.warning(f"🗑️ Orphaned zone detected: {domain_name} (zone {zone_id})")
                    
                    await execute_update(
                        """UPDATE domains 
                           SET cloudflare_zone_id = NULL, 
                               updated_at = CURRENT_TIMESTAMP 
                           WHERE id = %s""",
                        (domain_id,)
                    )
                    
                    await execute_update(
                        "DELETE FROM dns_records WHERE domain_name = %s",
                        (domain_name,)
                    )
                    
                    summary['orphaned_zones_cleaned'] += 1
                    logger.info(f"✅ Cleaned orphaned zone for {domain_name}")
                else:
                    cf_zone = cf_zone_data.get(zone_id, {})
                    cf_status = cf_zone.get('status', 'unknown')
                    db_status = db_zone.get('status')
                    
                    if cf_status != db_status and cf_status in ['active', 'pending', 'moved', 'deleted']:
                        await execute_update(
                            """UPDATE domains 
                               SET status = %s, updated_at = CURRENT_TIMESTAMP 
                               WHERE id = %s""",
                            (cf_status, domain_id)
                        )
                        summary['zone_status_updates'] += 1
                        logger.info(f"📝 Updated zone status for {domain_name}: {db_status} → {cf_status}")
            
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            summary['duration_seconds'] = duration
            
            self._stats['total_runs'] += 1
            self._stats['zones_checked'] += summary['zones_checked']
            self._stats['orphaned_zones_cleaned'] += summary['orphaned_zones_cleaned']
            self._stats['zone_status_updates'] += summary['zone_status_updates']
            self._last_run = datetime.now(timezone.utc)
            
            logger.info(f"✅ Zone reconciliation complete: {summary['zones_checked']} checked, "
                       f"{summary['orphaned_zones_cleaned']} orphaned cleaned, "
                       f"{summary['zone_status_updates']} status updates in {duration:.1f}s")
            
            if notify_admin:
                await self._notify_admin(summary)
                
        except Exception as e:
            summary['errors'].append(str(e))
            self._stats['last_error'] = str(e)
            logger.error(f"❌ Zone reconciliation failed: {e}")
        finally:
            self._running = False
        
        return summary
    
    async def _notify_admin(self, summary: Dict):
        """Log admin notification about reconciliation results"""
        try:
            message = (
                f"🔄 Zone Reconciliation Report - "
                f"Zones checked: {summary['zones_checked']}, "
                f"Orphans cleaned: {summary['orphaned_zones_cleaned']}, "
                f"Status updates: {summary['zone_status_updates']}, "
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


zone_reconciliation = ZoneReconciliationService()


async def run_zone_reconciliation():
    """Entry point for scheduled zone reconciliation job"""
    logger.info("📅 Scheduled Cloudflare zone reconciliation starting...")
    result = await zone_reconciliation.reconcile_all_zones(notify_admin=True)
    return result
