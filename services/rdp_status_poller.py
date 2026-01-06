"""
RDP Server Status Polling Service
Synchronizes Vultr instance states with rdp_servers table
Handles provisioning, running, reinstalling, and stopped states
"""

import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from decimal import Decimal

from database import execute_query, execute_update
from services.vultr import VultrService

logger = logging.getLogger(__name__)


class RDPStatusPoller:
    """
    Background service for polling RDP server statuses from Vultr API
    and updating the database with current power status and instance state
    """
    
    def __init__(self):
        self.vultr = VultrService()
        self.batch_size = 50
        self.stats = {
            'checked': 0,
            'updated': 0,
            'errors': 0,
            'transitions': {}
        }
        logger.info("🔄 RDPStatusPoller initialized: poll interval 3min, batch size 50")
    
    async def run_cycle(self) -> Dict[str, Any]:
        """
        Main polling cycle - called by APScheduler every 3 minutes
        
        Returns:
            Statistics about the polling cycle
        """
        try:
            logger.info("🔍 RDP STATUS POLL: Starting status synchronization cycle")
            
            # Reset statistics
            self._reset_stats()
            
            # Get servers that need status checking
            servers = await self._get_servers_to_poll()
            
            if not servers:
                logger.info("✅ RDP STATUS POLL: No servers need status checking")
                return {"status": "success", "message": "No servers to poll", "stats": self.stats}
            
            logger.info(f"📊 RDP STATUS POLL: Found {len(servers)} servers to check")
            
            # Poll each server (query already limits to batch_size)
            for server in servers:
                await self._poll_server_status(server)
            
            # Log summary
            logger.info(
                f"✅ RDP STATUS POLL: Cycle complete - "
                f"Checked: {self.stats['checked']}, "
                f"Updated: {self.stats['updated']}, "
                f"Errors: {self.stats['errors']}"
            )
            
            if self.stats['transitions']:
                logger.info(f"📊 Status transitions: {self.stats['transitions']}")
            
            return {
                "status": "success",
                "stats": self.stats
            }
            
        except Exception as e:
            logger.error(f"❌ RDP STATUS POLL: Critical error in polling cycle: {e}")
            return {
                "status": "error",
                "error": str(e),
                "stats": self.stats
            }
    
    async def _get_servers_to_poll(self) -> List[Dict[str, Any]]:
        """
        Get RDP servers that need status checking (round-robin based on last_polled_at)
        
        Criteria:
        - Status is provisioning, active, reinstalling, or suspending
        - OR power_status is starting, reinstalling, or stopping
        - AND deleted_at IS NULL
        - Ordered by last_polled_at (NULL first) for round-robin coverage
        
        Returns:
            List of server records
        """
        query = """
            SELECT 
                id,
                vultr_instance_id,
                status,
                power_status,
                public_ip,
                admin_password_encrypted,
                activated_at,
                last_polled_at
            FROM rdp_servers
            WHERE deleted_at IS NULL
              AND (
                  status IN ('provisioning', 'active', 'reinstalling', 'suspending')
                  OR power_status IN ('starting', 'reinstalling', 'stopping')
              )
            ORDER BY last_polled_at NULLS FIRST, id ASC
            LIMIT %s
        """
        
        try:
            results = await execute_query(query, (self.batch_size,))
            return results if results else []
        except Exception as e:
            logger.error(f"❌ Failed to fetch servers for polling: {e}")
            return []
    
    async def _poll_server_status(self, server: Dict[str, Any]) -> bool:
        """
        Poll a single server's status from Vultr API and update database
        
        Args:
            server: Server record from database
            
        Returns:
            True if successful, False otherwise
        """
        server_id = server['id']
        vultr_id = server['vultr_instance_id']
        current_status = server['status']
        current_power = server['power_status']
        
        try:
            self.stats['checked'] += 1
            
            # Get current status from Vultr API (async to avoid blocking event loop)
            instance, http_status = await asyncio.to_thread(self.vultr.get_instance, vultr_id)
            
            if instance is None:
                if http_status == 404:
                    logger.warning(f"⚠️ RDP {server_id}: Instance {vultr_id} confirmed deleted (404) - marking as deleted in database")
                    
                    # Server confirmed deleted at Vultr - mark as deleted in database
                    # This handles cases where the server was deleted externally or deletion failed to update DB
                    update_query = """
                        UPDATE rdp_servers
                        SET deleted_at = %s, status = 'deleted', auto_renew = false
                        WHERE id = %s AND deleted_at IS NULL
                    """
                    
                    await execute_update(update_query, (datetime.now(timezone.utc), server_id))
                    logger.info(f"✅ RDP {server_id}: Marked as deleted in database (orphaned record cleanup)")
                    self.stats['updated'] += 1
                    self._record_transition(current_status, 'deleted')
                    return True
                else:
                    logger.warning(f"⚠️ RDP {server_id}: Failed to get instance from Vultr (status={http_status}) - skipping (may be transient error)")
                    self.stats['errors'] += 1
                    return False
            
            # Extract Vultr status
            vultr_status = instance.get('status')  # active, pending, etc.
            vultr_power = instance.get('power_status')  # running, starting, stopped, reinstalling
            vultr_ip = instance.get('main_ip')
            
            # Determine what needs updating
            updates = []
            new_status = current_status
            new_power = current_power
            
            # Handle status transitions
            if current_status == 'provisioning' and vultr_status == 'active' and vultr_ip:
                # Server is now active
                new_status = 'active'
                updates.append("status = 'active'")
                
                # Set activated_at if not already set
                if not server.get('activated_at'):
                    updates.append(f"activated_at = '{datetime.now(timezone.utc).isoformat()}'")
                
                logger.info(f"✅ RDP {server_id}: Provisioning complete → Active")
                self._record_transition('provisioning', 'active')
            
            # Handle power status transitions
            if vultr_power and vultr_power != current_power:
                new_power = vultr_power
                updates.append(f"power_status = '{vultr_power}'")
                
                logger.info(f"🔄 RDP {server_id}: Power status changed: {current_power} → {vultr_power}")
                self._record_transition(f"power:{current_power}", f"power:{vultr_power}")
            
            # Handle reinstalling status
            if vultr_power == 'reinstalling' and current_status != 'reinstalling':
                new_status = 'reinstalling'
                updates.append("status = 'reinstalling'")
                logger.info(f"🔄 RDP {server_id}: Server is being reinstalled")
                self._record_transition(current_status, 'reinstalling')
            
            # Server finished reinstalling
            if current_status == 'reinstalling' and vultr_power == 'running':
                new_status = 'active'
                updates.append("status = 'active'")
                logger.info(f"✅ RDP {server_id}: Reinstall complete → Active")
                self._record_transition('reinstalling', 'active')
            
            # Handle suspension completion
            if current_status == 'suspending' and vultr_power == 'stopped':
                new_status = 'suspended'
                updates.append("status = 'suspended'")
                updates.append(f"suspended_at = '{datetime.now(timezone.utc).isoformat()}'")
                logger.info(f"✅ RDP {server_id}: Suspension complete → Suspended")
                self._record_transition('suspending', 'suspended')
            
            # Update IP if changed
            if vultr_ip and vultr_ip != server.get('public_ip'):
                updates.append(f"public_ip = '{vultr_ip}'")
                logger.info(f"📍 RDP {server_id}: IP updated to {vultr_ip}")
            
            # Always update last_polled_at to track round-robin progress
            updates.append(f"last_polled_at = '{datetime.now(timezone.utc).isoformat()}'")
            
            # Apply updates if any changes detected
            if updates:
                update_query = f"""
                    UPDATE rdp_servers
                    SET {', '.join(updates)}
                    WHERE id = %s
                """
                
                await execute_update(update_query, (server_id,))
                self.stats['updated'] += 1
                
                logger.info(
                    f"✅ RDP {server_id}: Updated - "
                    f"Status: {current_status} → {new_status}, "
                    f"Power: {current_power} → {new_power}"
                )
            else:
                logger.debug(f"➡️ RDP {server_id}: No changes detected")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ RDP {server_id}: Error polling status: {e}")
            self.stats['errors'] += 1
            return False
    
    def _record_transition(self, from_state: str, to_state: str):
        """Record a status transition for statistics"""
        transition_key = f"{from_state} → {to_state}"
        self.stats['transitions'][transition_key] = self.stats['transitions'].get(transition_key, 0) + 1
    
    def _reset_stats(self):
        """Reset statistics for new cycle"""
        self.stats = {
            'checked': 0,
            'updated': 0,
            'errors': 0,
            'transitions': {}
        }


# Global instance for APScheduler
_rdp_status_poller = None


def get_rdp_status_poller() -> RDPStatusPoller:
    """Get or create the global RDP status poller instance"""
    global _rdp_status_poller
    if _rdp_status_poller is None:
        _rdp_status_poller = RDPStatusPoller()
    return _rdp_status_poller


async def run_rdp_status_polling() -> Dict[str, Any]:
    """
    Entry point for APScheduler
    Runs the RDP status polling cycle
    """
    poller = get_rdp_status_poller()
    return await poller.run_cycle()
