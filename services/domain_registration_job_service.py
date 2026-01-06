"""
Domain and Hosting Registration Job Service

Handles async/background domain and hosting registration to ensure webhooks respond instantly.
Registration is queued and processed in the background, preventing webhook timeouts.
"""

import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from decimal import Decimal

logger = logging.getLogger(__name__)


class HostingOrderJobService:
    """Service for managing async hosting order jobs."""
    
    RETRY_INTERVALS = [0, 60, 300, 900]
    
    def __init__(self):
        self.is_processing = False
        self._processing_lock = asyncio.Lock()
    
    async def enqueue_hosting(
        self,
        order_id: int,
        user_id: int,
        domain_name: str,
        payment_details: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """Queue a hosting order for async processing."""
        from database import execute_query, execute_update
        
        try:
            order_id_str = str(order_id)
            
            existing = await execute_query("""
                SELECT id, status FROM hosting_order_jobs
                WHERE order_id = %s
            """, (order_id_str,))
            
            if existing:
                job = existing[0]
                if job['status'] == 'completed':
                    logger.info(f"✅ Hosting job already completed for order {order_id}")
                    return job['id']
                elif job['status'] in ('pending', 'processing'):
                    logger.info(f"⏳ Hosting job already queued for order {order_id}")
                    return job['id']
                else:
                    await execute_update("""
                        UPDATE hosting_order_jobs
                        SET status = 'pending', retry_count = 0,
                            next_attempt_at = NOW(), last_error = NULL,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (job['id'],))
                    logger.info(f"♻️ Reset failed hosting job for order {order_id}")
                    return job['id']
            
            payment_json = json.dumps(payment_details, cls=DecimalEncoder) if payment_details else None
            
            await execute_update("""
                INSERT INTO hosting_order_jobs 
                (order_id, user_id, domain_name, payment_details)
                VALUES (%s, %s, %s, %s)
            """, (order_id_str, user_id, domain_name, payment_json))
            
            result = await execute_query("""
                SELECT id FROM hosting_order_jobs WHERE order_id = %s
            """, (order_id_str,))
            
            if result:
                job_id = result[0]['id']
                logger.info(f"📋 Queued hosting job #{job_id} for {domain_name} (order: {order_id})")
                return job_id
            return None
            
        except Exception as e:
            logger.error(f"❌ Error queuing hosting job: {e}")
            return None
    
    async def get_pending_jobs(self, limit: int = 5) -> List[Dict]:
        """Get pending jobs ready for processing."""
        from database import execute_query
        
        try:
            jobs = await execute_query("""
                SELECT id, order_id, user_id, domain_name, payment_details,
                       retry_count, max_retries, created_at
                FROM hosting_order_jobs
                WHERE status = 'pending'
                AND next_attempt_at <= NOW()
                AND retry_count < max_retries
                ORDER BY created_at ASC
                LIMIT %s
            """, (limit,))
            return jobs or []
        except Exception as e:
            logger.error(f"❌ Error fetching pending hosting jobs: {e}")
            return []
    
    async def claim_job(self, job_id: int) -> bool:
        """Atomically claim a job for processing."""
        from database import execute_update
        
        try:
            rows = await execute_update("""
                UPDATE hosting_order_jobs
                SET status = 'processing', updated_at = NOW()
                WHERE id = %s AND status = 'pending'
            """, (job_id,))
            return rows > 0
        except Exception as e:
            logger.error(f"❌ Error claiming hosting job {job_id}: {e}")
            return False
    
    async def complete_job(self, job_id: int, result: Dict[str, Any]) -> bool:
        """Mark a job as completed."""
        from database import execute_update
        
        try:
            result_json = json.dumps(result, cls=DecimalEncoder)
            rows = await execute_update("""
                UPDATE hosting_order_jobs
                SET status = 'completed', result = %s,
                    completed_at = NOW(), updated_at = NOW()
                WHERE id = %s
            """, (result_json, job_id))
            return rows > 0
        except Exception as e:
            logger.error(f"❌ Error completing hosting job {job_id}: {e}")
            return False
    
    async def fail_job(self, job_id: int, error: str, retry: bool = True) -> bool:
        """Mark a job as failed, optionally scheduling retry."""
        from database import execute_query, execute_update
        
        try:
            job = await execute_query("""
                SELECT retry_count, max_retries FROM hosting_order_jobs WHERE id = %s
            """, (job_id,))
            
            if not job:
                return False
            
            retry_count = job[0]['retry_count']
            max_retries = job[0]['max_retries']
            new_retry_count = retry_count + 1
            
            if retry and new_retry_count < max_retries:
                interval_idx = min(new_retry_count, len(self.RETRY_INTERVALS) - 1)
                retry_seconds = self.RETRY_INTERVALS[interval_idx]
                
                rows = await execute_update("""
                    UPDATE hosting_order_jobs
                    SET status = 'pending', retry_count = %s, last_error = %s,
                        next_attempt_at = NOW() + INTERVAL '%s seconds',
                        updated_at = NOW()
                    WHERE id = %s
                """, (new_retry_count, error, retry_seconds, job_id))
                logger.info(f"📋 Scheduled hosting retry #{new_retry_count} for job {job_id}")
            else:
                rows = await execute_update("""
                    UPDATE hosting_order_jobs
                    SET status = 'failed', retry_count = %s, last_error = %s,
                        completed_at = NOW(), updated_at = NOW()
                    WHERE id = %s
                """, (new_retry_count, error, job_id))
                logger.error(f"❌ Hosting job {job_id} permanently failed: {error}")
                
            return rows > 0
        except Exception as e:
            logger.error(f"❌ Error failing hosting job {job_id}: {e}")
            return False
    
    async def process_job(self, job: Dict) -> bool:
        """Process a single hosting job."""
        job_id = job['id']
        order_id = int(job['order_id'])
        user_id = job['user_id']
        domain_name = job['domain_name']
        payment_details = job.get('payment_details') or {}
        
        if isinstance(payment_details, str):
            try:
                payment_details = json.loads(payment_details)
            except:
                payment_details = {}
        
        logger.info(f"🔄 Processing hosting job #{job_id}: {domain_name} for user {user_id}")
        
        try:
            from services.hosting_orchestrator import HostingBundleOrchestrator
            from webhook_handler import WebhookQueryAdapter
            
            orchestrator = HostingBundleOrchestrator()
            query_adapter = WebhookQueryAdapter(user_id)
            
            await orchestrator.start_hosting_bundle(
                order_id=order_id,
                user_id=user_id,
                domain_name=domain_name,
                payment_details=payment_details,
                query_adapter=query_adapter
            )
            
            await self.complete_job(job_id, {'success': True})
            logger.info(f"✅ Hosting job #{job_id} completed successfully for {domain_name}")
            return True
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Hosting job #{job_id} error: {error_msg}")
            await self.fail_job(job_id, error_msg)
            return False
    
    async def process_pending_jobs(self) -> int:
        """Process all pending hosting jobs."""
        if self.is_processing:
            return 0
        
        async with self._processing_lock:
            self.is_processing = True
            processed = 0
            
            try:
                jobs = await self.get_pending_jobs(limit=3)
                
                for job in jobs:
                    if await self.claim_job(job['id']):
                        await self.process_job(job)
                        processed += 1
                
                if processed > 0:
                    logger.info(f"📊 Processed {processed} hosting jobs")
                    
            except Exception as e:
                logger.error(f"❌ Error in hosting job processor: {e}")
            finally:
                self.is_processing = False
            
            return processed


_hosting_job_service: Optional[HostingOrderJobService] = None


def get_hosting_order_job_service() -> HostingOrderJobService:
    """Get the singleton hosting job service instance."""
    global _hosting_job_service
    if _hosting_job_service is None:
        _hosting_job_service = HostingOrderJobService()
    return _hosting_job_service


async def run_hosting_order_job_processor():
    """APScheduler-compatible wrapper for hosting order job processing."""
    service = get_hosting_order_job_service()
    try:
        processed = await service.process_pending_jobs()
        if processed > 0:
            logger.info(f"📋 Hosting order processor: completed {processed} jobs")
    except Exception as e:
        logger.error(f"❌ Hosting order processor error: {e}")


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class DomainRegistrationJobService:
    """Service for managing async domain registration jobs."""
    
    RETRY_INTERVALS = [0, 60, 300, 900]
    
    def __init__(self):
        self.is_processing = False
        self._processing_lock = asyncio.Lock()
    
    async def enqueue_registration(
        self,
        order_id: str,
        user_id: int,
        domain_name: str,
        payment_details: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """
        Queue a domain registration for async processing.
        
        Returns job ID if created, None on error.
        """
        from database import execute_query, execute_update
        
        try:
            existing = await execute_query("""
                SELECT id, status FROM domain_registration_jobs
                WHERE order_id = %s
            """, (order_id,))
            
            if existing:
                job = existing[0]
                if job['status'] == 'completed':
                    logger.info(f"✅ Registration job already completed for order {order_id}")
                    return job['id']
                elif job['status'] in ('pending', 'processing'):
                    logger.info(f"⏳ Registration job already queued for order {order_id}")
                    return job['id']
                else:
                    await execute_update("""
                        UPDATE domain_registration_jobs
                        SET status = 'pending', retry_count = 0,
                            next_attempt_at = NOW(), last_error = NULL,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (job['id'],))
                    logger.info(f"♻️ Reset failed registration job for order {order_id}")
                    return job['id']
            
            payment_json = json.dumps(payment_details, cls=DecimalEncoder) if payment_details else None
            
            await execute_update("""
                INSERT INTO domain_registration_jobs 
                (order_id, user_id, domain_name, payment_details)
                VALUES (%s, %s, %s, %s)
            """, (order_id, user_id, domain_name, payment_json))
            
            result = await execute_query("""
                SELECT id FROM domain_registration_jobs WHERE order_id = %s
            """, (order_id,))
            
            if result:
                job_id = result[0]['id']
                logger.info(f"📋 Queued domain registration job #{job_id} for {domain_name} (order: {order_id})")
                return job_id
            return None
            
        except Exception as e:
            logger.error(f"❌ Error queuing domain registration job: {e}")
            return None
    
    async def get_pending_jobs(self, limit: int = 5) -> List[Dict]:
        """Get pending jobs ready for processing."""
        from database import execute_query
        
        try:
            jobs = await execute_query("""
                SELECT id, order_id, user_id, domain_name, payment_details,
                       retry_count, max_retries, created_at
                FROM domain_registration_jobs
                WHERE status = 'pending'
                AND next_attempt_at <= NOW()
                AND retry_count < max_retries
                ORDER BY created_at ASC
                LIMIT %s
            """, (limit,))
            return jobs or []
        except Exception as e:
            logger.error(f"❌ Error fetching pending registration jobs: {e}")
            return []
    
    async def claim_job(self, job_id: int) -> bool:
        """Atomically claim a job for processing."""
        from database import execute_update
        
        try:
            rows = await execute_update("""
                UPDATE domain_registration_jobs
                SET status = 'processing', updated_at = NOW()
                WHERE id = %s AND status = 'pending'
            """, (job_id,))
            return rows > 0
        except Exception as e:
            logger.error(f"❌ Error claiming registration job {job_id}: {e}")
            return False
    
    async def complete_job(self, job_id: int, result: Dict[str, Any]) -> bool:
        """Mark a job as completed."""
        from database import execute_update
        
        try:
            result_json = json.dumps(result, cls=DecimalEncoder)
            rows = await execute_update("""
                UPDATE domain_registration_jobs
                SET status = 'completed', result = %s,
                    completed_at = NOW(), updated_at = NOW()
                WHERE id = %s
            """, (result_json, job_id))
            return rows > 0
        except Exception as e:
            logger.error(f"❌ Error completing registration job {job_id}: {e}")
            return False
    
    async def fail_job(self, job_id: int, error: str, retry: bool = True) -> bool:
        """Mark a job as failed, optionally scheduling retry."""
        from database import execute_query, execute_update
        
        try:
            job = await execute_query("""
                SELECT retry_count, max_retries FROM domain_registration_jobs WHERE id = %s
            """, (job_id,))
            
            if not job:
                return False
            
            retry_count = job[0]['retry_count']
            max_retries = job[0]['max_retries']
            new_retry_count = retry_count + 1
            
            if retry and new_retry_count < max_retries:
                interval_idx = min(new_retry_count, len(self.RETRY_INTERVALS) - 1)
                retry_seconds = self.RETRY_INTERVALS[interval_idx]
                
                rows = await execute_update("""
                    UPDATE domain_registration_jobs
                    SET status = 'pending', retry_count = %s, last_error = %s,
                        next_attempt_at = NOW() + INTERVAL '%s seconds',
                        updated_at = NOW()
                    WHERE id = %s
                """, (new_retry_count, error, retry_seconds, job_id))
                logger.info(f"📋 Scheduled retry #{new_retry_count} for job {job_id} in {retry_seconds}s")
            else:
                rows = await execute_update("""
                    UPDATE domain_registration_jobs
                    SET status = 'failed', retry_count = %s, last_error = %s,
                        completed_at = NOW(), updated_at = NOW()
                    WHERE id = %s
                """, (new_retry_count, error, job_id))
                logger.error(f"❌ Job {job_id} permanently failed: {error}")
                
            return rows > 0
        except Exception as e:
            logger.error(f"❌ Error failing registration job {job_id}: {e}")
            return False
    
    async def process_job(self, job: Dict) -> bool:
        """Process a single registration job."""
        job_id = job['id']
        order_id = job['order_id']
        user_id = job['user_id']
        domain_name = job['domain_name']
        payment_details = job.get('payment_details') or {}
        
        if isinstance(payment_details, str):
            try:
                payment_details = json.loads(payment_details)
            except:
                payment_details = {}
        
        logger.info(f"🔄 Processing registration job #{job_id}: {domain_name} for user {user_id}")
        
        try:
            from services.registration_orchestrator import start_domain_registration
            from webhook_handler import WebhookQueryAdapter
            
            result = await start_domain_registration(
                order_id=order_id,
                user_id=user_id,
                domain_name=domain_name,
                payment_details=payment_details,
                query_adapter=WebhookQueryAdapter(user_id)
            )
            
            if result and result.get('success'):
                await self.complete_job(job_id, result)
                logger.info(f"✅ Registration job #{job_id} completed successfully for {domain_name}")
                return True
            else:
                error = result.get('error', 'Registration failed') if result else 'No result'
                await self.fail_job(job_id, error)
                return False
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Registration job #{job_id} error: {error_msg}")
            await self.fail_job(job_id, error_msg)
            return False
    
    async def process_pending_jobs(self) -> int:
        """Process all pending registration jobs. Returns count of jobs processed."""
        if self.is_processing:
            logger.debug("⏳ Job processor already running, skipping")
            return 0
        
        async with self._processing_lock:
            self.is_processing = True
            processed = 0
            
            try:
                jobs = await self.get_pending_jobs(limit=3)
                
                for job in jobs:
                    if await self.claim_job(job['id']):
                        await self.process_job(job)
                        processed += 1
                
                if processed > 0:
                    logger.info(f"📊 Processed {processed} domain registration jobs")
                    
            except Exception as e:
                logger.error(f"❌ Error in job processor: {e}")
            finally:
                self.is_processing = False
            
            return processed


_domain_job_service: Optional[DomainRegistrationJobService] = None


def get_domain_registration_job_service() -> DomainRegistrationJobService:
    """Get the singleton job service instance."""
    global _domain_job_service
    if _domain_job_service is None:
        _domain_job_service = DomainRegistrationJobService()
    return _domain_job_service


async def start_domain_registration_processor(interval_seconds: int = 5):
    """
    Background task that processes pending domain registration jobs.
    Should be started as asyncio.create_task() during app startup.
    """
    service = get_domain_registration_job_service()
    logger.info(f"🚀 Domain registration job processor started (interval: {interval_seconds}s)")
    
    while True:
        try:
            await service.process_pending_jobs()
        except Exception as e:
            logger.error(f"❌ Domain registration processor error: {e}")
        
        await asyncio.sleep(interval_seconds)


async def run_domain_registration_job_processor():
    """APScheduler-compatible wrapper for domain registration job processing."""
    service = get_domain_registration_job_service()
    try:
        processed = await service.process_pending_jobs()
        if processed > 0:
            logger.info(f"📋 Domain registration processor: completed {processed} jobs")
    except Exception as e:
        logger.error(f"❌ Domain registration processor error: {e}")
