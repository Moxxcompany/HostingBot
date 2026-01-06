"""
cPanel Account Reconciliation Service

Syncs cPanel/WHM account status with the local database.
Detects accounts that have been deleted, suspended, or modified externally.
"""
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class CPanelReconciliationService:
    """Service to reconcile cPanel accounts between database and WHM server"""
    
    def __init__(self):
        self._running = False
        self._last_run: Optional[datetime] = None
        self._stats = {
            'total_runs': 0,
            'accounts_checked': 0,
            'orphaned_accounts': 0,
            'status_updates': 0,
            'suspension_syncs': 0,
            'last_error': None
        }
    
    async def reconcile_all_accounts(self, notify_admin: bool = False) -> Dict:
        """
        Reconcile all cPanel accounts in the database with WHM server.
        
        Returns:
            Summary of reconciliation results
        """
        from services.cpanel import CPanelService
        from database import execute_query, execute_update
        
        cpanel = CPanelService()
        
        start_time = datetime.now(timezone.utc)
        self._running = True
        
        summary = {
            'accounts_checked': 0,
            'orphaned_accounts': 0,
            'status_updates': 0,
            'suspension_syncs': 0,
            'disk_usage_updates': 0,
            'errors': [],
            'duration_seconds': 0
        }
        
        try:
            logger.info("🔄 Starting cPanel account reconciliation...")
            
            whm_accounts = await asyncio.to_thread(cpanel.list_accounts)
            
            if whm_accounts is None:
                summary['errors'].append("Failed to fetch accounts from WHM")
                logger.error("❌ Failed to fetch accounts from WHM API")
                return summary
            
            whm_usernames: Set[str] = set()
            whm_account_data: Dict[str, Dict] = {}
            
            for account in whm_accounts:
                username = account.get('user') or account.get('username')
                if username:
                    whm_usernames.add(username)
                    whm_account_data[username] = account
            
            logger.info(f"📊 Found {len(whm_usernames)} accounts on WHM server")
            
            db_subscriptions = await execute_query(
                """SELECT hs.id, hs.cpanel_username, hs.status, hs.domain_name, hs.user_id
                   FROM hosting_subscriptions hs
                   WHERE hs.cpanel_username IS NOT NULL
                   AND hs.status NOT IN ('deleted', 'cancelled', 'terminated')"""
            )
            
            if not db_subscriptions:
                logger.info("ℹ️ No active hosting subscriptions with cPanel accounts")
                return summary
            
            for subscription in db_subscriptions:
                summary['accounts_checked'] += 1
                cpanel_username = subscription.get('cpanel_username')
                sub_id = subscription.get('id')
                db_status = subscription.get('status')
                domain_name = subscription.get('domain_name')
                
                if cpanel_username not in whm_usernames:
                    logger.warning(f"🗑️ Orphaned cPanel account: {cpanel_username} for {domain_name}")
                    
                    await execute_update(
                        """UPDATE hosting_subscriptions 
                           SET status = 'deleted_externally', 
                               updated_at = CURRENT_TIMESTAMP 
                           WHERE id = %s""",
                        (sub_id,)
                    )
                    
                    summary['orphaned_accounts'] += 1
                else:
                    whm_account = whm_account_data.get(cpanel_username, {})
                    is_suspended = whm_account.get('suspended', False) or whm_account.get('suspendreason')
                    
                    if is_suspended and db_status == 'active':
                        await execute_update(
                            """UPDATE hosting_subscriptions 
                               SET status = 'suspended', 
                                   suspended_at = CURRENT_TIMESTAMP,
                                   updated_at = CURRENT_TIMESTAMP 
                               WHERE id = %s""",
                            (sub_id,)
                        )
                        summary['suspension_syncs'] += 1
                        logger.info(f"📝 Synced suspension status for {cpanel_username}")
                    
                    elif not is_suspended and db_status == 'suspended':
                        await execute_update(
                            """UPDATE hosting_subscriptions 
                               SET status = 'active', 
                                   suspended_at = NULL,
                                   updated_at = CURRENT_TIMESTAMP 
                               WHERE id = %s""",
                            (sub_id,)
                        )
                        summary['status_updates'] += 1
                        logger.info(f"📝 Synced unsuspension status for {cpanel_username}")
                    
                    disk_used = whm_account.get('diskused') or whm_account.get('disk_used')
                    if disk_used:
                        await execute_update(
                            """UPDATE hosting_subscriptions 
                               SET disk_usage = %s, 
                                   updated_at = CURRENT_TIMESTAMP 
                               WHERE id = %s""",
                            (disk_used, sub_id)
                        )
                        summary['disk_usage_updates'] += 1
            
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            summary['duration_seconds'] = duration
            
            self._stats['total_runs'] += 1
            self._stats['accounts_checked'] += summary['accounts_checked']
            self._stats['orphaned_accounts'] += summary['orphaned_accounts']
            self._stats['status_updates'] += summary['status_updates']
            self._stats['suspension_syncs'] += summary['suspension_syncs']
            self._last_run = datetime.now(timezone.utc)
            
            logger.info(f"✅ cPanel reconciliation complete: {summary['accounts_checked']} checked, "
                       f"{summary['orphaned_accounts']} orphaned, "
                       f"{summary['suspension_syncs']} suspension syncs in {duration:.1f}s")
            
            if notify_admin:
                await self._notify_admin(summary)
                
        except Exception as e:
            summary['errors'].append(str(e))
            self._stats['last_error'] = str(e)
            logger.error(f"❌ cPanel reconciliation failed: {e}")
        finally:
            self._running = False
        
        return summary
    
    async def _notify_admin(self, summary: Dict):
        """Log admin notification about reconciliation results"""
        try:
            message = (
                f"🔄 cPanel Reconciliation Report - "
                f"Accounts checked: {summary['accounts_checked']}, "
                f"Orphaned: {summary['orphaned_accounts']}, "
                f"Suspension syncs: {summary['suspension_syncs']}, "
                f"Status updates: {summary['status_updates']}, "
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


    async def reconcile_addon_domains(self) -> Dict:
        """
        Reconcile addon domains between cPanel and pending jobs.
        
        Detects addon domains that were deleted externally from cPanel
        and resets their jobs to 'pending' (if not intentionally cancelled).
        
        Returns:
            Summary of reconciliation results
        """
        from services.cpanel import CPanelService
        from database import execute_query, execute_update
        
        cpanel = CPanelService()
        start_time = datetime.now(timezone.utc)
        
        summary = {
            'subscriptions_checked': 0,
            'addon_domains_synced': 0,
            'jobs_reset': 0,
            'orphaned_jobs': 0,
            'errors': [],
            'duration_seconds': 0
        }
        
        try:
            logger.info("🔄 Starting addon domain reconciliation...")
            
            active_subs = await execute_query("""
                SELECT id, cpanel_username, domain_name 
                FROM hosting_subscriptions 
                WHERE cpanel_username IS NOT NULL 
                AND status = 'active'
            """)
            
            if not active_subs:
                logger.info("ℹ️ No active hosting subscriptions to reconcile")
                return summary
            
            for sub in active_subs:
                summary['subscriptions_checked'] += 1
                sub_id = sub['id']
                cpanel_username = sub['cpanel_username']
                
                cpanel_addons = await cpanel.list_addon_domains(cpanel_username)
                cpanel_domains: Set[str] = set()
                
                if cpanel_addons and cpanel_addons.get('addon_domains'):
                    for addon in cpanel_addons['addon_domains']:
                        if addon.get('domain'):
                            cpanel_domains.add(addon['domain'].lower())
                
                completed_jobs = await execute_query("""
                    SELECT id, addon_domain, status 
                    FROM addon_domain_pending_jobs 
                    WHERE subscription_id = %s AND status = 'completed'
                """, (sub_id,))
                
                for job in completed_jobs or []:
                    addon_domain = job['addon_domain'].lower()
                    
                    if addon_domain not in cpanel_domains:
                        await execute_update("""
                            UPDATE addon_domain_pending_jobs
                            SET status = 'pending', retry_count = 0, 
                                next_attempt_at = NOW(), last_error = 'Reset by reconciliation - domain missing from cPanel',
                                updated_at = NOW()
                            WHERE id = %s
                        """, (job['id'],))
                        summary['jobs_reset'] += 1
                        logger.info(f"♻️ Reset addon domain job for {addon_domain} - missing from cPanel")
            
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            summary['duration_seconds'] = duration
            
            logger.info(f"✅ Addon domain reconciliation complete: "
                       f"{summary['subscriptions_checked']} subs checked, "
                       f"{summary['jobs_reset']} jobs reset in {duration:.1f}s")
            
        except Exception as e:
            summary['errors'].append(str(e))
            logger.error(f"❌ Addon domain reconciliation failed: {e}")
        
        return summary


cpanel_reconciliation = CPanelReconciliationService()


async def run_cpanel_reconciliation():
    """Entry point for scheduled cPanel reconciliation job"""
    logger.info("📅 Scheduled cPanel account reconciliation starting...")
    result = await cpanel_reconciliation.reconcile_all_accounts(notify_admin=True)
    return result


async def run_addon_domain_reconciliation():
    """Entry point for scheduled addon domain reconciliation job"""
    logger.info("📅 Scheduled addon domain reconciliation starting...")
    result = await cpanel_reconciliation.reconcile_addon_domains()
    return result
