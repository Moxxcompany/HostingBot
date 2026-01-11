#!/usr/bin/env python3
"""
Enhanced Payment Cleanup Service - Background scheduler for automated payment cleanup
Runs every 30 minutes to clean up expired payment intents

Enhanced Features:
- Cryptocurrency-specific timeout periods (Bitcoin: 1h, others: 30min)  
- Grace period handling for network delays (5 minutes)
- Safety checks prevent expiration of recently created payments
- User notifications via Telegram for expired payments
- Comprehensive audit trail and monitoring
"""

import asyncio
import logging
import time
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from database import (
    cleanup_stale_and_expired_payments, 
    cleanup_expired_hosting_intents, 
    cleanup_failed_hosting_orders,
    cleanup_failed_domain_orders,
    cleanup_stale_domain_intents,
    cleanup_failed_rdp_orders,
    get_db_executor
)

logger = logging.getLogger(__name__)

class PaymentCleanupService:
    """
    Background service that runs payment cleanup operations on a schedule
    
    Features:
    - Runs cleanup every 30 minutes
    - Comprehensive error handling and recovery
    - Graceful shutdown support
    - Performance monitoring and metrics
    - Configurable cleanup intervals
    """
    
    def __init__(self, cleanup_interval_minutes: int = 30):
        self.cleanup_interval = cleanup_interval_minutes * 60  # Convert to seconds
        self.running = False
        self.cleanup_task: Optional[asyncio.Task] = None
        self.stats = {
            'total_cleanups': 0,
            'total_payments_cleaned': 0,
            'last_cleanup_time': None,
            'last_cleanup_duration': 0,
            'total_errors': 0,
            'service_start_time': None
        }
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"🛑 CLEANUP SERVICE: Received signal {signum}, initiating graceful shutdown...")
        self.stop()
    
    async def start(self):
        """Start the cleanup service"""
        if self.running:
            logger.warning("⚠️ CLEANUP SERVICE: Service is already running")
            return
        
        self.running = True
        self.stats['service_start_time'] = datetime.utcnow()
        
        logger.info("🚀 CLEANUP SERVICE: Starting automated payment cleanup service")
        logger.info(f"   • Cleanup interval: {self.cleanup_interval // 60} minutes")
        logger.info(f"   • Service started at: {self.stats['service_start_time']}")
        
        # Start the cleanup loop
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        try:
            await self.cleanup_task
        except asyncio.CancelledError:
            logger.info("📴 CLEANUP SERVICE: Service stopped")
        except Exception as e:
            logger.error(f"❌ CLEANUP SERVICE: Critical service error: {e}")
            raise
    
    def stop(self):
        """Stop the cleanup service"""
        if not self.running:
            return
        
        self.running = False
        
        if self.cleanup_task and not self.cleanup_task.done():
            logger.info("🛑 CLEANUP SERVICE: Cancelling cleanup task...")
            self.cleanup_task.cancel()
        
        self._log_service_summary()
    
    async def _cleanup_loop(self):
        """Main cleanup loop that runs every 30 minutes"""
        logger.info("🔄 CLEANUP SERVICE: Cleanup loop started")
        
        # Run initial cleanup after 1 minute to allow system to stabilize
        await asyncio.sleep(60)
        
        while self.running:
            try:
                await self._run_cleanup_cycle()
                
                # Wait for next cleanup cycle
                if self.running:
                    logger.info(f"⏰ CLEANUP SERVICE: Next cleanup in {self.cleanup_interval // 60} minutes")
                    await asyncio.sleep(self.cleanup_interval)
                    
            except asyncio.CancelledError:
                logger.info("📴 CLEANUP SERVICE: Cleanup loop cancelled")
                break
            except Exception as e:
                self.stats['total_errors'] += 1
                logger.error(f"❌ CLEANUP SERVICE: Error in cleanup cycle: {e}")
                logger.error(f"   Total errors so far: {self.stats['total_errors']}")
                
                # Wait a shorter interval on error to retry sooner
                if self.running:
                    error_retry_interval = min(300, self.cleanup_interval // 6)  # Max 5 minutes or 1/6 of normal interval
                    logger.info(f"   Retrying in {error_retry_interval // 60} minutes due to error")
                    await asyncio.sleep(error_retry_interval)
    
    async def _run_cleanup_cycle(self):
        """Run a single cleanup cycle"""
        cycle_start = time.time()
        self.stats['last_cleanup_time'] = datetime.utcnow()
        
        logger.info("🧹 CLEANUP SERVICE: Starting cleanup cycle")
        logger.info(f"   • Cycle #{self.stats['total_cleanups'] + 1}")
        logger.info(f"   • Time: {self.stats['last_cleanup_time']}")
        
        try:
            # Run the actual cleanup - payment intents
            cleaned_count = await cleanup_stale_and_expired_payments()
            
            # Also cleanup hosting intents and orders
            hosting_intents_cleaned = await cleanup_expired_hosting_intents()
            hosting_orders_cleaned = await cleanup_failed_hosting_orders()
            
            # Domain cleanup
            domain_orders_cleaned = await cleanup_failed_domain_orders()
            domain_intents_cleaned = await cleanup_stale_domain_intents()
            
            # RDP cleanup
            rdp_orders_cleaned = await cleanup_failed_rdp_orders()
            
            total_cleaned = (cleaned_count + hosting_intents_cleaned + hosting_orders_cleaned + 
                           domain_orders_cleaned + domain_intents_cleaned + rdp_orders_cleaned)
            
            # Update statistics
            self.stats['total_cleanups'] += 1
            self.stats['total_payments_cleaned'] += total_cleaned
            self.stats['last_cleanup_duration'] = time.time() - cycle_start
            
            # Log cycle completion
            logger.info(f"✅ CLEANUP SERVICE: Cycle completed successfully")
            logger.info(f"   • Payments cleaned: {cleaned_count}")
            logger.info(f"   • Hosting intents/orders: {hosting_intents_cleaned}/{hosting_orders_cleaned}")
            logger.info(f"   • Domain intents/orders: {domain_intents_cleaned}/{domain_orders_cleaned}")
            logger.info(f"   • RDP orders: {rdp_orders_cleaned}")
            logger.info(f"   • Cycle duration: {self.stats['last_cleanup_duration']:.2f}s")
            logger.info(f"   • Total cleaned this cycle: {total_cleaned}")
            
            # Send admin notification for significant cleanup activity
            if total_cleaned >= 10:
                try:
                    from admin_alerts import send_warning_alert
                    await send_warning_alert(
                        "Payment Cleanup Service",
                        f"Automated cleanup processed {cleaned_count} payments",
                        "database",
                        {
                            "cleaned_count": cleaned_count,
                            "cycle_duration": self.stats['last_cleanup_duration'],
                            "total_cleanups": self.stats['total_cleanups'],
                            "total_cleaned": self.stats['total_payments_cleaned']
                        }
                    )
                except Exception as alert_error:
                    logger.warning(f"⚠️ Failed to send cleanup service alert: {alert_error}")
            
        except Exception as e:
            self.stats['total_errors'] += 1
            logger.error(f"❌ CLEANUP SERVICE: Cleanup cycle failed: {e}")
            logger.error(f"   Cycle duration before error: {time.time() - cycle_start:.2f}s")
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        stats = self.stats.copy()
        
        if stats['service_start_time']:
            stats['uptime_hours'] = (datetime.utcnow() - stats['service_start_time']).total_seconds() / 3600
            
        if stats['total_cleanups'] > 0:
            stats['avg_payments_per_cleanup'] = stats['total_payments_cleaned'] / stats['total_cleanups']
            
        stats['is_running'] = self.running
        stats['cleanup_interval_minutes'] = self.cleanup_interval // 60
        
        return stats
    
    def _log_service_summary(self):
        """Log service summary on shutdown"""
        stats = self.get_stats()
        
        logger.info("📊 CLEANUP SERVICE: Final service summary")
        logger.info(f"   • Total cleanup cycles: {stats['total_cleanups']}")
        logger.info(f"   • Total payments cleaned: {stats['total_payments_cleaned']}")
        logger.info(f"   • Total errors: {stats['total_errors']}")
        logger.info(f"   • Service uptime: {stats.get('uptime_hours', 0):.1f} hours")
        logger.info(f"   • Average payments per cleanup: {stats.get('avg_payments_per_cleanup', 0):.1f}")


# Global service instance
_cleanup_service: Optional[PaymentCleanupService] = None

async def start_payment_cleanup_service(cleanup_interval_minutes: int = 30) -> PaymentCleanupService:
    """Start the payment cleanup service"""
    global _cleanup_service
    
    if _cleanup_service and _cleanup_service.running:
        logger.warning("⚠️ Payment cleanup service is already running")
        return _cleanup_service
    
    _cleanup_service = PaymentCleanupService(cleanup_interval_minutes)
    
    # Start the service in the background - use ensure_future for better task management
    asyncio.ensure_future(_cleanup_service.start())
    
    logger.info("🚀 Payment cleanup service started successfully")
    return _cleanup_service

def stop_payment_cleanup_service():
    """Stop the payment cleanup service"""
    global _cleanup_service
    
    if _cleanup_service:
        _cleanup_service.stop()
        logger.info("🛑 Payment cleanup service stopped")
    else:
        logger.info("ℹ️ Payment cleanup service was not running")

def get_cleanup_service_stats() -> Optional[Dict[str, Any]]:
    """Get cleanup service statistics"""
    if _cleanup_service:
        return _cleanup_service.get_stats()
    return None

async def run_manual_cleanup() -> int:
    """Run a manual cleanup cycle (useful for testing or immediate cleanup)"""
    logger.info("🔧 MANUAL CLEANUP: Running manual payment cleanup")
    result = await cleanup_stale_and_expired_payments()
    logger.info(f"✅ MANUAL CLEANUP: Completed, cleaned {result} payments")
    return result

# CLI interface for standalone operation
if __name__ == "__main__":
    async def main():
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        logger.info("🧹 STANDALONE CLEANUP SERVICE: Starting...")
        
        # Check command line arguments
        if len(sys.argv) > 1:
            if sys.argv[1] == "--manual":
                # Run manual cleanup once
                result = await run_manual_cleanup()
                logger.info(f"✅ Manual cleanup completed: {result} payments cleaned")
                return
            elif sys.argv[1] == "--interval":
                # Custom interval
                try:
                    interval = int(sys.argv[2])
                    logger.info(f"🔧 Using custom interval: {interval} minutes")
                except (IndexError, ValueError):
                    logger.error("❌ Invalid interval specified, using default 30 minutes")
                    interval = 30
            else:
                interval = 30
        else:
            interval = 30
        
        # Start the service
        service = PaymentCleanupService(interval)
        try:
            await service.start()
        except KeyboardInterrupt:
            logger.info("👋 STANDALONE CLEANUP SERVICE: Shutting down...")
            service.stop()
        except Exception as e:
            logger.error(f"❌ STANDALONE CLEANUP SERVICE: Fatal error: {e}")
            service.stop()
            raise
    
    # Run the service
    asyncio.run(main())
