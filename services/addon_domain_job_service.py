"""
Addon Domain Job Service

Handles automatic retry of adding external addon domains to cPanel.
When dns_only mode is used, this service queues the domain and automatically
retries adding it to cPanel every 10 minutes until DNS propagates.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from database import execute_query, execute_update

logger = logging.getLogger(__name__)


class AddonDomainJobService:
    """Service for managing pending addon domain jobs."""
    
    # Retry intervals (in minutes) for each attempt
    # More frequent checks early on for faster DNS propagation detection
    RETRY_INTERVALS = [1, 2, 2, 2, 5, 10, 30, 60]
    
    def __init__(self):
        self.default_max_retries = 8
    
    async def enqueue_addon_domain(
        self,
        subscription_id: int,
        user_id: int,
        addon_domain: str,
        domain_type: str = 'external',
        subdomain: Optional[str] = None,
        document_root: Optional[str] = None,
        zone_id: Optional[str] = None
    ) -> Optional[int]:
        """
        Queue an addon domain for automatic cPanel addition.
        
        Args:
            subscription_id: The hosting subscription ID
            user_id: The user ID
            addon_domain: The domain to add
            domain_type: Type of domain (external, existing, newly_registered)
            subdomain: Optional subdomain prefix
            document_root: Optional document root path
            zone_id: Cloudflare zone ID if available
            
        Returns:
            Job ID if created, None on error
        """
        try:
            existing = await execute_query("""
                SELECT id, status FROM addon_domain_pending_jobs
                WHERE subscription_id = %s AND addon_domain = %s
            """, (subscription_id, addon_domain))
            
            if existing:
                if existing[0]['status'] in ('completed', 'failed', 'cancelled'):
                    await execute_update("""
                        UPDATE addon_domain_pending_jobs
                        SET status = 'pending', retry_count = 0, 
                            next_attempt_at = NOW(), last_error = NULL,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (existing[0]['id'],))
                    logger.info(f"♻️ Reset existing addon domain job for {addon_domain} (was {existing[0]['status']})")
                    return existing[0]['id']
                else:
                    logger.info(f"⏳ Addon domain job already pending for {addon_domain}")
                    return existing[0]['id']
            
            await execute_update("""
                INSERT INTO addon_domain_pending_jobs 
                (subscription_id, user_id, addon_domain, domain_type, subdomain, document_root, zone_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (subscription_id, user_id, addon_domain, domain_type, subdomain, document_root, zone_id))
            
            result = await execute_query("""
                SELECT id FROM addon_domain_pending_jobs 
                WHERE subscription_id = %s AND addon_domain = %s
            """, (subscription_id, addon_domain))
            
            if result:
                job_id = result[0]['id']
                logger.info(f"📋 Queued addon domain job #{job_id} for {addon_domain} on subscription {subscription_id}")
                return job_id
            return None
            
        except Exception as e:
            logger.error(f"❌ Error queuing addon domain job: {e}")
            return None
    
    async def get_pending_jobs(self) -> List[Dict]:
        """Get all pending jobs that are ready for retry."""
        try:
            jobs = await execute_query("""
                SELECT j.*, hs.cpanel_username, hs.server_ip
                FROM addon_domain_pending_jobs j
                JOIN hosting_subscriptions hs ON j.subscription_id = hs.id
                WHERE j.status IN ('pending', 'pending_dns_propagation')
                AND hs.status = 'active'
                AND j.next_attempt_at <= NOW()
                AND j.retry_count < j.max_retries
                ORDER BY j.next_attempt_at ASC
                LIMIT 10
            """, ())
            return jobs or []
        except Exception as e:
            logger.error(f"❌ Error getting pending addon domain jobs: {e}")
            return []
    
    async def check_nameserver_propagation(self, addon_domain: str) -> Dict:
        """
        Check if domain nameservers have been updated to Cloudflare.
        
        Returns:
            Dict with 'propagated' (bool), 'current_nameservers' (list), and 'expected_nameservers' (list)
        """
        from services.dns_resolver import dns_resolver
        from services.cloudflare import cloudflare
        
        try:
            current_ns = await dns_resolver.get_nameservers(addon_domain)
            expected_ns = await cloudflare.get_account_nameservers()
            
            if not current_ns:
                logger.debug(f"🔍 Could not resolve nameservers for {addon_domain}")
                return {
                    'propagated': False,
                    'current_nameservers': [],
                    'expected_nameservers': list(expected_ns),
                    'reason': 'Could not resolve nameservers'
                }
            
            current_ns_lower = [ns.lower() for ns in current_ns]
            expected_ns_lower = [ns.lower() for ns in expected_ns]
            
            propagated = all(ns in current_ns_lower for ns in expected_ns_lower)
            
            # Detect Cloudflare NS mismatch (using different Cloudflare account)
            is_cloudflare_ns = any('cloudflare.com' in ns.lower() for ns in current_ns)
            is_wrong_cloudflare = is_cloudflare_ns and not propagated
            
            logger.info(f"🔍 DNS check for {addon_domain}: propagated={propagated}, current={current_ns}")
            
            if is_wrong_cloudflare:
                reason = f"Domain uses different Cloudflare nameservers. Please update to: {', '.join(expected_ns)}"
            elif propagated:
                reason = 'Nameservers match'
            else:
                reason = 'Nameservers not yet updated'
            
            return {
                'propagated': propagated,
                'current_nameservers': current_ns,
                'expected_nameservers': list(expected_ns),
                'reason': reason,
                'is_cloudflare_mismatch': is_wrong_cloudflare
            }
            
        except Exception as e:
            logger.warning(f"⚠️ Error checking nameserver propagation for {addon_domain}: {e}")
            return {
                'propagated': False,
                'current_nameservers': [],
                'expected_nameservers': [],
                'reason': str(e)
            }

    async def process_pending_jobs(self) -> Dict:
        """
        Process all pending addon domain jobs.
        First checks DNS propagation, then attempts to add each domain to cPanel.
        
        Returns:
            Summary of processed jobs
        """
        from services.cpanel import CPanelService
        
        jobs = await self.get_pending_jobs()
        if not jobs:
            logger.debug("📋 No pending addon domain jobs to process")
            return {'processed': 0, 'success': 0, 'failed': 0, 'retrying': 0, 'dns_pending': 0}
        
        logger.info(f"🔄 Processing {len(jobs)} pending addon domain jobs")
        
        cpanel = CPanelService()
        results = {'processed': 0, 'success': 0, 'failed': 0, 'retrying': 0, 'dns_pending': 0}
        
        for job in jobs:
            results['processed'] += 1
            job_id = job['id']
            addon_domain = job['addon_domain']
            cpanel_username = job['cpanel_username']
            subscription_id = job['subscription_id']
            user_id = job['user_id']
            retry_count = job['retry_count']
            
            logger.info(f"🔄 Processing addon domain job #{job_id}: {addon_domain} (attempt {retry_count + 1})")
            
            # Step 1: Check DNS propagation before attempting cPanel add
            dns_check = await self.check_nameserver_propagation(addon_domain)
            
            if not dns_check.get('propagated'):
                logger.info(f"⏳ DNS not yet propagated for {addon_domain}: {dns_check.get('reason')}")
                await self._handle_retry(
                    job_id, 
                    addon_domain, 
                    retry_count, 
                    f"DNS not propagated: {dns_check.get('reason')}. Current NS: {dns_check.get('current_nameservers')}"
                )
                
                if retry_count + 1 >= job['max_retries']:
                    results['failed'] += 1
                    await self._notify_user(user_id, addon_domain, subscription_id, success=False, 
                                          error=f"Nameservers not updated after {retry_count + 1} attempts. Current: {dns_check.get('current_nameservers')}")
                else:
                    results['dns_pending'] += 1
                continue
            
            logger.info(f"✅ DNS propagated for {addon_domain}, attempting cPanel add")
            
            # Step 2: DNS is propagated, attempt to add to cPanel
            # Always skip DNS check since we use Cloudflare for DNS management (external DNS)
            # This bypasses cPanel's "domain points to IP not using server DNS" validation
            try:
                addon_result = await cpanel.add_addon_domain(
                    cpanel_username,
                    addon_domain,
                    subdomain=job.get('subdomain'),
                    document_root=job.get('document_root'),
                    skip_dns_check=True  # Skip cPanel's DNS server validation - we use Cloudflare
                )
                
                if addon_result and addon_result.get('success'):
                    rows_updated = await execute_update("""
                        UPDATE addon_domain_pending_jobs
                        SET status = 'completed', completed_at = NOW(), updated_at = NOW()
                        WHERE id = %s AND status NOT IN ('cancelled', 'completed')
                    """, (job_id,))
                    
                    if rows_updated == 0:
                        logger.warning(f"⚠️ Addon domain {addon_domain} job #{job_id} was cancelled during processing - domain added but job not marked complete")
                        continue
                    
                    logger.info(f"✅ Addon domain {addon_domain} successfully added to cPanel for subscription {subscription_id}")
                    results['success'] += 1
                    
                    await self._notify_user(user_id, addon_domain, subscription_id, success=True)
                    
                else:
                    error_msg = addon_result.get('error', 'Unknown error') if addon_result else 'No response from cPanel'
                    await self._handle_retry(job_id, addon_domain, retry_count, error_msg)
                    
                    if retry_count + 1 >= job['max_retries']:
                        results['failed'] += 1
                        await self._notify_user(user_id, addon_domain, subscription_id, success=False, error=error_msg)
                    else:
                        results['retrying'] += 1
                        
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Error processing addon domain job #{job_id}: {error_msg}")
                await self._handle_retry(job_id, addon_domain, retry_count, error_msg)
                
                if retry_count + 1 >= job['max_retries']:
                    results['failed'] += 1
                else:
                    results['retrying'] += 1
        
        logger.info(f"📊 Addon domain job processing complete: {results}")
        return results
    
    async def _handle_retry(self, job_id: int, addon_domain: str, retry_count: int, error_msg: str):
        """Handle retry logic for failed addon domain additions with exponential backoff."""
        new_retry_count = retry_count + 1
        interval_index = min(retry_count, len(self.RETRY_INTERVALS) - 1)
        retry_interval = self.RETRY_INTERVALS[interval_index]
        next_attempt = datetime.utcnow() + timedelta(minutes=retry_interval)
        
        rows_updated = await execute_update("""
            UPDATE addon_domain_pending_jobs
            SET retry_count = %s, next_attempt_at = %s, last_error = %s, 
                updated_at = NOW(), status = CASE WHEN %s >= max_retries THEN 'failed' ELSE status END
            WHERE id = %s AND status NOT IN ('cancelled', 'completed')
        """, (new_retry_count, next_attempt, error_msg, new_retry_count, job_id))
        
        if rows_updated == 0:
            logger.info(f"⏹️ Addon domain {addon_domain} job #{job_id} was cancelled - skipping retry")
        else:
            logger.info(f"⏳ Addon domain {addon_domain} job #{job_id} retry in {retry_interval}min at {next_attempt} (attempt {new_retry_count})")
    
    async def _notify_user(self, user_id: int, addon_domain: str, subscription_id: int, success: bool, error: Optional[str] = None):
        """Send notification to user about addon domain status."""
        try:
            user_data = await execute_query("""
                SELECT telegram_id FROM users WHERE id = %s
            """, (user_id,))
            
            if not user_data or not user_data[0].get('telegram_id'):
                return
                
            telegram_id = user_data[0]['telegram_id']
            
            if success:
                message = (
                    f"✅ **Addon Domain Added**\n\n"
                    f"Your addon domain `{addon_domain}` has been successfully added to your hosting subscription #{subscription_id}.\n\n"
                    f"The domain is now active and ready to use."
                )
            else:
                message = (
                    f"❌ **Addon Domain Failed**\n\n"
                    f"We were unable to add addon domain `{addon_domain}` to your hosting subscription #{subscription_id} after multiple attempts.\n\n"
                    f"Error: {error}\n\n"
                    f"Please ensure your domain's nameservers are correctly configured and try again via the API."
                )
            
            from notifications import queue_user_message
            await queue_user_message(telegram_id, message)
            logger.info(f"📧 Sent addon domain notification to user {user_id}")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not send addon domain notification: {e}")
    
    async def get_job_status(self, subscription_id: int, addon_domain: str) -> Optional[Dict]:
        """Get the status of a specific addon domain job."""
        try:
            result = await execute_query("""
                SELECT * FROM addon_domain_pending_jobs
                WHERE subscription_id = %s AND addon_domain = %s
            """, (subscription_id, addon_domain))
            return result[0] if result else None
        except Exception as e:
            logger.error(f"❌ Error getting addon domain job status: {e}")
            return None
    
    async def cancel_job(self, job_id: int) -> bool:
        """Cancel a pending addon domain job."""
        try:
            await execute_update("""
                UPDATE addon_domain_pending_jobs
                SET status = 'cancelled', updated_at = NOW()
                WHERE id = %s AND status = 'pending'
            """, (job_id,))
            logger.info(f"🚫 Cancelled addon domain job #{job_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error cancelling addon domain job: {e}")
            return False


addon_domain_job_service = AddonDomainJobService()


async def run_addon_domain_job_processor():
    """Scheduled job to process pending addon domain additions."""
    try:
        logger.info("🔄 Running addon domain job processor...")
        results = await addon_domain_job_service.process_pending_jobs()
        if results['processed'] > 0:
            logger.info(f"📊 Addon domain jobs: {results['success']} success, {results['retrying']} retrying, {results['failed']} failed")
    except Exception as e:
        logger.error(f"❌ Addon domain job processor error: {e}")
