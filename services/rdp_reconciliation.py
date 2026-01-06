"""
Vultr/RDP Server Reconciliation Service

Syncs RDP server status with Vultr API.
Detects servers that have been deleted, stopped, or modified externally.
"""
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class RDPReconciliationService:
    """Service to reconcile RDP servers between database and Vultr API"""
    
    def __init__(self):
        self._running = False
        self._last_run: Optional[datetime] = None
        self._stats = {
            'total_runs': 0,
            'servers_checked': 0,
            'orphaned_servers': 0,
            'status_updates': 0,
            'ip_updates': 0,
            'last_error': None
        }
    
    async def reconcile_all_servers(self, notify_admin: bool = False) -> Dict:
        """
        Reconcile all RDP servers in the database with Vultr API.
        
        Returns:
            Summary of reconciliation results
        """
        from database import execute_query, execute_update
        
        start_time = datetime.now(timezone.utc)
        self._running = True
        
        summary = {
            'servers_checked': 0,
            'orphaned_servers': 0,
            'status_updates': 0,
            'ip_updates': 0,
            'power_state_updates': 0,
            'errors': [],
            'duration_seconds': 0
        }
        
        try:
            logger.info("🔄 Starting RDP server reconciliation...")
            
            try:
                from services.vultr import VultrService
                vultr = VultrService()
            except Exception as e:
                summary['errors'].append(f"Vultr service unavailable: {e}")
                logger.warning(f"⚠️ Vultr service not available: {e}")
                return summary
            
            vultr_instances = vultr.list_instances()
            
            if vultr_instances is None:
                summary['errors'].append("Failed to fetch instances from Vultr")
                logger.error("❌ Failed to fetch instances from Vultr API")
                return summary
            
            vultr_instance_ids: Set[str] = set()
            vultr_instance_data: Dict[str, Dict] = {}
            
            for instance in vultr_instances:
                instance_id = instance.get('id')
                if instance_id:
                    vultr_instance_ids.add(instance_id)
                    vultr_instance_data[instance_id] = instance
            
            logger.info(f"📊 Found {len(vultr_instance_ids)} instances on Vultr")
            
            db_servers = await execute_query(
                """SELECT id, vultr_instance_id, status, public_ip, user_id, plan_id
                   FROM rdp_servers
                   WHERE vultr_instance_id IS NOT NULL
                   AND status NOT IN ('deleted', 'terminated', 'destroyed')"""
            )
            
            if not db_servers:
                logger.info("ℹ️ No active RDP servers with Vultr instances")
                return summary
            
            for server in db_servers:
                summary['servers_checked'] += 1
                vultr_id = server.get('vultr_instance_id')
                server_id = server.get('id')
                db_status = server.get('status')
                db_ip = server.get('public_ip')
                
                if vultr_id not in vultr_instance_ids:
                    logger.warning(f"🗑️ Orphaned RDP server: {vultr_id} (DB ID: {server_id})")
                    
                    await execute_update(
                        """UPDATE rdp_servers 
                           SET status = 'deleted_externally', 
                               updated_at = CURRENT_TIMESTAMP 
                           WHERE id = %s""",
                        (server_id,)
                    )
                    
                    summary['orphaned_servers'] += 1
                else:
                    vultr_instance = vultr_instance_data.get(vultr_id, {})
                    vultr_status = vultr_instance.get('status', '').lower()
                    vultr_power = vultr_instance.get('power_status', '').lower()
                    vultr_ip = vultr_instance.get('main_ip')
                    
                    new_status = None
                    if vultr_status == 'active' and vultr_power == 'running':
                        new_status = 'running'
                    elif vultr_status == 'active' and vultr_power == 'stopped':
                        new_status = 'stopped'
                    elif vultr_status == 'pending':
                        new_status = 'provisioning'
                    elif vultr_status == 'suspended':
                        new_status = 'suspended'
                    
                    if new_status and new_status != db_status:
                        await execute_update(
                            """UPDATE rdp_servers 
                               SET status = %s, 
                                   updated_at = CURRENT_TIMESTAMP 
                               WHERE id = %s""",
                            (new_status, server_id)
                        )
                        summary['status_updates'] += 1
                        logger.info(f"📝 Updated RDP server status: {db_status} → {new_status}")
                    
                    if vultr_ip and vultr_ip != db_ip and vultr_ip != '0.0.0.0':
                        await execute_update(
                            """UPDATE rdp_servers 
                               SET public_ip = %s, 
                                   updated_at = CURRENT_TIMESTAMP 
                               WHERE id = %s""",
                            (vultr_ip, server_id)
                        )
                        summary['ip_updates'] += 1
                        logger.info(f"📝 Updated RDP server IP: {db_ip} → {vultr_ip}")
            
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            summary['duration_seconds'] = duration
            
            self._stats['total_runs'] += 1
            self._stats['servers_checked'] += summary['servers_checked']
            self._stats['orphaned_servers'] += summary['orphaned_servers']
            self._stats['status_updates'] += summary['status_updates']
            self._stats['ip_updates'] += summary['ip_updates']
            self._last_run = datetime.now(timezone.utc)
            
            logger.info(f"✅ RDP reconciliation complete: {summary['servers_checked']} checked, "
                       f"{summary['orphaned_servers']} orphaned, "
                       f"{summary['status_updates']} status updates in {duration:.1f}s")
            
            if notify_admin:
                await self._notify_admin(summary)
                
        except Exception as e:
            summary['errors'].append(str(e))
            self._stats['last_error'] = str(e)
            logger.error(f"❌ RDP reconciliation failed: {e}")
        finally:
            self._running = False
        
        return summary
    
    async def _notify_admin(self, summary: Dict):
        """Log admin notification about reconciliation results"""
        try:
            message = (
                f"🔄 RDP Reconciliation Report - "
                f"Servers checked: {summary['servers_checked']}, "
                f"Orphaned: {summary['orphaned_servers']}, "
                f"Status updates: {summary['status_updates']}, "
                f"IP updates: {summary['ip_updates']}, "
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


rdp_reconciliation = RDPReconciliationService()


async def run_rdp_reconciliation():
    """Entry point for scheduled RDP reconciliation job"""
    logger.info("📅 Scheduled RDP server reconciliation starting...")
    result = await rdp_reconciliation.reconcile_all_servers(notify_admin=True)
    return result
