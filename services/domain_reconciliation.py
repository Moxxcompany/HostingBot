"""
Domain Registration Reconciliation Service

Syncs domain registration status with OpenProvider.
Detects domains that have been modified, transferred, or expired externally.
"""
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DomainReconciliationService:
    """Service to reconcile domain registration status with OpenProvider"""
    
    def __init__(self):
        self._running = False
        self._last_run: Optional[datetime] = None
        self._stats = {
            'total_runs': 0,
            'domains_checked': 0,
            'status_updates': 0,
            'expiry_updates': 0,
            'orphaned_domains': 0,
            'last_error': None
        }
    
    async def reconcile_domain(self, domain_name: str, provider_domain_id: str) -> Dict:
        """
        Reconcile a single domain with OpenProvider.
        
        Args:
            domain_name: The domain name to reconcile
            provider_domain_id: The OpenProvider domain ID
            
        Returns:
            Dict with reconciliation results
        """
        from services.openprovider import OpenProviderService
        from database import execute_update, execute_query
        openprovider = OpenProviderService()
        
        result = {
            'domain': domain_name,
            'status_updated': False,
            'expiry_updated': False,
            'orphaned': False,
            'errors': []
        }
        
        try:
            op_domain = await openprovider.get_domain_details(domain_name)
            
            if op_domain is None or op_domain.get('error'):
                error_msg = op_domain.get('error', 'Domain not found') if op_domain else 'Domain not found'
                
                if 'not found' in str(error_msg).lower() or 'does not exist' in str(error_msg).lower():
                    result['orphaned'] = True
                    logger.warning(f"🗑️ Orphaned domain detected: {domain_name} not found in OpenProvider")
                    
                    await execute_update(
                        """UPDATE domains 
                           SET status = 'not_found', 
                               provider_domain_id = NULL,
                               updated_at = CURRENT_TIMESTAMP 
                           WHERE domain_name = %s""",
                        (domain_name,)
                    )
                else:
                    result['errors'].append(error_msg)
                
                return result
            
            op_status = op_domain.get('status', '').lower()
            op_expiry = op_domain.get('expiration_date') or op_domain.get('renewal_date')
            op_nameservers = op_domain.get('nameservers', [])
            
            db_domain = await execute_query(
                "SELECT status, expiry_date, nameservers FROM domains WHERE domain_name = %s",
                (domain_name,)
            )
            
            if db_domain:
                db_record = db_domain[0]
                db_status = db_record.get('status', '').lower()
                
                if op_status and op_status != db_status:
                    await execute_update(
                        """UPDATE domains 
                           SET status = %s, updated_at = CURRENT_TIMESTAMP 
                           WHERE domain_name = %s""",
                        (op_status, domain_name)
                    )
                    result['status_updated'] = True
                    logger.info(f"📝 Updated domain status for {domain_name}: {db_status} → {op_status}")
                
                if op_expiry:
                    await execute_update(
                        """UPDATE domains 
                           SET expiry_date = %s, updated_at = CURRENT_TIMESTAMP 
                           WHERE domain_name = %s""",
                        (op_expiry, domain_name)
                    )
                    result['expiry_updated'] = True
                    
        except Exception as e:
            result['errors'].append(str(e))
            logger.error(f"❌ Error reconciling domain {domain_name}: {e}")
        
        return result
    
    async def reconcile_all_domains(self, notify_admin: bool = False) -> Dict:
        """
        Reconcile all domains in the database with OpenProvider.
        
        Args:
            notify_admin: Whether to send admin notification with results
            
        Returns:
            Summary of reconciliation across all domains
        """
        from database import execute_query
        
        start_time = datetime.now(timezone.utc)
        self._running = True
        
        summary = {
            'domains_checked': 0,
            'status_updates': 0,
            'expiry_updates': 0,
            'orphaned_domains': 0,
            'errors': [],
            'duration_seconds': 0
        }
        
        try:
            logger.info("🔄 Starting domain registration reconciliation...")
            
            domains = await execute_query(
                """SELECT domain_name, provider_domain_id 
                   FROM domains 
                   WHERE provider_domain_id IS NOT NULL 
                   AND status NOT IN ('deleted', 'not_found', 'transferred_away')"""
            )
            
            if not domains:
                logger.info("ℹ️ No domains with provider IDs to reconcile")
                return summary
            
            logger.info(f"📊 Found {len(domains)} domains to reconcile with OpenProvider")
            
            for domain in domains:
                domain_name = domain.get('domain_name')
                provider_id = domain.get('provider_domain_id')
                
                if not domain_name or not provider_id:
                    continue
                
                result = await self.reconcile_domain(domain_name, provider_id)
                summary['domains_checked'] += 1
                
                if result['status_updated']:
                    summary['status_updates'] += 1
                if result['expiry_updated']:
                    summary['expiry_updates'] += 1
                if result['orphaned']:
                    summary['orphaned_domains'] += 1
                if result['errors']:
                    summary['errors'].extend(result['errors'])
                
                await asyncio.sleep(0.5)
            
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            summary['duration_seconds'] = duration
            
            self._stats['total_runs'] += 1
            self._stats['domains_checked'] += summary['domains_checked']
            self._stats['status_updates'] += summary['status_updates']
            self._stats['expiry_updates'] += summary['expiry_updates']
            self._stats['orphaned_domains'] += summary['orphaned_domains']
            self._last_run = datetime.now(timezone.utc)
            
            logger.info(f"✅ Domain reconciliation complete: {summary['domains_checked']} checked, "
                       f"{summary['status_updates']} status updates, "
                       f"{summary['expiry_updates']} expiry updates, "
                       f"{summary['orphaned_domains']} orphaned in {duration:.1f}s")
            
            if notify_admin:
                await self._notify_admin(summary)
                
        except Exception as e:
            summary['errors'].append(str(e))
            self._stats['last_error'] = str(e)
            logger.error(f"❌ Domain reconciliation failed: {e}")
        finally:
            self._running = False
        
        return summary
    
    async def check_expiring_domains(self, days_ahead: int = 30) -> List[Dict]:
        """Check for domains expiring soon"""
        from database import execute_query
        
        try:
            expiry_threshold = datetime.now(timezone.utc) + timedelta(days=days_ahead)
            
            expiring = await execute_query(
                """SELECT d.domain_name, d.expiry_date, d.user_id, u.telegram_id
                   FROM domains d
                   JOIN users u ON d.user_id = u.id
                   WHERE d.expiry_date IS NOT NULL 
                   AND d.expiry_date <= %s
                   AND d.status NOT IN ('deleted', 'not_found', 'transferred_away')
                   ORDER BY d.expiry_date ASC""",
                (expiry_threshold,)
            )
            
            return expiring or []
            
        except Exception as e:
            logger.error(f"❌ Failed to check expiring domains: {e}")
            return []
    
    async def _notify_admin(self, summary: Dict):
        """Log admin notification about reconciliation results"""
        try:
            message = (
                f"🔄 Domain Reconciliation Report - "
                f"Domains checked: {summary['domains_checked']}, "
                f"Status updates: {summary['status_updates']}, "
                f"Expiry updates: {summary['expiry_updates']}, "
                f"Orphaned: {summary['orphaned_domains']}, "
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


domain_reconciliation = DomainReconciliationService()


async def run_domain_reconciliation():
    """Entry point for scheduled domain reconciliation job"""
    logger.info("📅 Scheduled domain registration reconciliation starting...")
    result = await domain_reconciliation.reconcile_all_domains(notify_admin=True)
    return result
