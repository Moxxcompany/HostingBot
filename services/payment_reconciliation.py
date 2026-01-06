"""
Payment Intent Reconciliation Service

Verifies pending payment intents with payment providers (DynoPay/BlockBee).
Detects payments that may have been confirmed but webhook failed.
"""
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PaymentReconciliationService:
    """Service to reconcile payment intents with external payment providers"""
    
    def __init__(self):
        self._running = False
        self._last_run: Optional[datetime] = None
        self._stats = {
            'total_runs': 0,
            'intents_checked': 0,
            'confirmed_recovered': 0,
            'expired_cleaned': 0,
            'provider_errors': 0,
            'last_error': None
        }
    
    async def reconcile_pending_payments(self, hours_old: int = 2, notify_admin: bool = False) -> Dict:
        """
        Reconcile pending payment intents older than specified hours.
        
        Args:
            hours_old: Only check intents older than this many hours
            notify_admin: Whether to send admin notification
            
        Returns:
            Summary of reconciliation results
        """
        from database import execute_query, execute_update
        
        start_time = datetime.now(timezone.utc)
        self._running = True
        
        summary = {
            'intents_checked': 0,
            'confirmed_recovered': 0,
            'expired_cleaned': 0,
            'still_pending': 0,
            'provider_errors': 0,
            'errors': [],
            'duration_seconds': 0
        }
        
        try:
            logger.info(f"🔄 Starting payment reconciliation (intents > {hours_old}h old)...")
            
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_old)
            max_age = datetime.now(timezone.utc) - timedelta(hours=48)
            
            pending_intents = await execute_query(
                """SELECT id, uuid_id, order_id, payment_provider, payment_address, 
                          amount, currency, status, created_at, user_id, order_type
                   FROM payment_intents
                   WHERE status IN ('pending', 'pending_payment', 'awaiting_confirmation')
                   AND created_at < %s
                   AND created_at > %s
                   ORDER BY created_at ASC
                   LIMIT 50""",
                (cutoff_time, max_age)
            )
            
            if not pending_intents:
                logger.info("ℹ️ No pending payment intents to reconcile")
                return summary
            
            logger.info(f"📊 Found {len(pending_intents)} pending intents to check")
            
            for intent in pending_intents:
                summary['intents_checked'] += 1
                intent_id = intent.get('id')
                provider = intent.get('payment_provider', '').lower()
                payment_address = intent.get('payment_address')
                order_id = intent.get('order_id')
                created_at = intent.get('created_at')
                
                try:
                    payment_status = await self._check_provider_status(
                        provider, payment_address, order_id
                    )
                    
                    if payment_status.get('confirmed'):
                        rows = await execute_update(
                            """UPDATE payment_intents 
                               SET status = 'confirmed_by_reconciliation',
                                   confirmed_at = CURRENT_TIMESTAMP,
                                   updated_at = CURRENT_TIMESTAMP
                               WHERE id = %s 
                               AND status IN ('pending', 'pending_payment', 'awaiting_confirmation')""",
                            (intent_id,)
                        )
                        if rows > 0:
                            summary['confirmed_recovered'] += 1
                            logger.info(f"✅ Recovered confirmed payment: intent {intent_id}")
                        else:
                            logger.debug(f"⏭️ Intent {intent_id} already processed by webhook")
                        
                    elif payment_status.get('expired'):
                        await execute_update(
                            """UPDATE payment_intents 
                               SET status = 'expired',
                                   updated_at = CURRENT_TIMESTAMP
                               WHERE id = %s
                               AND status IN ('pending', 'pending_payment', 'awaiting_confirmation')""",
                            (intent_id,)
                        )
                        summary['expired_cleaned'] += 1
                        
                    elif payment_status.get('error'):
                        summary['provider_errors'] += 1
                        
                    else:
                        summary['still_pending'] += 1
                        
                except Exception as e:
                    summary['provider_errors'] += 1
                    logger.warning(f"⚠️ Error checking intent {intent_id}: {e}")
                
                await asyncio.sleep(0.3)
            
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            summary['duration_seconds'] = duration
            
            self._stats['total_runs'] += 1
            self._stats['intents_checked'] += summary['intents_checked']
            self._stats['confirmed_recovered'] += summary['confirmed_recovered']
            self._stats['expired_cleaned'] += summary['expired_cleaned']
            self._stats['provider_errors'] += summary['provider_errors']
            self._last_run = datetime.now(timezone.utc)
            
            logger.info(f"✅ Payment reconciliation complete: {summary['intents_checked']} checked, "
                       f"{summary['confirmed_recovered']} recovered, "
                       f"{summary['expired_cleaned']} expired in {duration:.1f}s")
            
            if notify_admin and (summary['confirmed_recovered'] > 0 or summary['provider_errors'] > 0):
                await self._notify_admin(summary)
                
        except Exception as e:
            summary['errors'].append(str(e))
            self._stats['last_error'] = str(e)
            logger.error(f"❌ Payment reconciliation failed: {e}")
        finally:
            self._running = False
        
        return summary
    
    async def _check_provider_status(self, provider: str, address: str, order_id: str) -> Dict:
        """Check payment status with the provider"""
        result = {'confirmed': False, 'expired': False, 'error': None}
        
        try:
            if provider == 'blockbee':
                try:
                    from services.blockbee import blockbee_service
                    
                    status = await blockbee_service.check_payment_status(address)
                    if status and status.get('status') == 'confirmed':
                        result['confirmed'] = True
                    elif status and status.get('status') == 'expired':
                        result['expired'] = True
                except ImportError:
                    result['error'] = 'BlockBee service not available'
                except Exception as e:
                    result['error'] = str(e)
                    
            elif provider == 'dynopay':
                try:
                    from services.dynopay import dynopay_service
                    
                    status = await dynopay_service.check_payment_status(order_id)
                    if status and status.get('status') in ['confirmed', 'completed']:
                        result['confirmed'] = True
                    elif status and status.get('status') == 'expired':
                        result['expired'] = True
                except ImportError:
                    result['error'] = 'DynoPay service not available'
                except Exception as e:
                    result['error'] = str(e)
            else:
                result['error'] = f'Unknown provider: {provider}'
                
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    async def _notify_admin(self, summary: Dict):
        """Log admin notification about reconciliation results"""
        try:
            message = (
                f"🔄 Payment Reconciliation Report - "
                f"Checked: {summary['intents_checked']}, "
                f"Recovered: {summary['confirmed_recovered']}, "
                f"Expired: {summary['expired_cleaned']}, "
                f"Still pending: {summary['still_pending']}, "
                f"Provider errors: {summary['provider_errors']}, "
                f"Duration: {summary.get('duration_seconds', 0):.1f}s"
            )
            
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


payment_reconciliation = PaymentReconciliationService()


async def run_payment_reconciliation():
    """Entry point for scheduled payment reconciliation job"""
    logger.info("📅 Scheduled payment reconciliation starting...")
    result = await payment_reconciliation.reconcile_pending_payments(hours_old=2, notify_admin=True)
    return result
