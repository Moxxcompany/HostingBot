#!/usr/bin/env python3
"""
Webhook Monitoring System for Crypto Payment Processing
Prevents future webhook failures by monitoring webhook processing health

This system monitors:
- Webhook processing success rates
- Payment intent status distribution  
- Auth token validation failures
- Payment confirmation delays
- Provider-specific issues

Usage:
    python webhook_monitoring.py --health-check
    python webhook_monitoring.py --monitor --interval 300  # Monitor every 5 minutes
"""

import asyncio
import os
import sys
import logging
import argparse
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# Add current directory to path to import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import execute_query, execute_update
from admin_alerts import send_critical_alert, send_warning_alert, send_error_alert

# Configure logging
logging.basicConfig(
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    level=logging.INFO,
    force=True
)
logger = logging.getLogger(__name__)

class WebhookMonitor:
    """Webhook health monitoring and alerting system"""
    
    def __init__(self):
        # Alert thresholds
        self.stuck_payment_threshold = 5  # Alert if 5+ stuck payments
        self.webhook_failure_threshold = 0.8  # Alert if success rate < 80%
        self.payment_delay_threshold_hours = 2  # Alert if payments delayed > 2 hours
        
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive webhook and payment processing health check"""
        try:
            logger.info("🏥 Starting webhook system health check...")
            
            health_status = {
                'timestamp': datetime.utcnow().isoformat(),
                'overall_status': 'healthy',
                'issues': [],
                'warnings': [],
                'metrics': {}
            }
            
            # 1. Check stuck payments
            stuck_metrics = await self._check_stuck_payments()
            health_status['metrics']['stuck_payments'] = stuck_metrics
            
            if stuck_metrics['count'] >= self.stuck_payment_threshold:
                health_status['issues'].append(f"High number of stuck payments: {stuck_metrics['count']} (${stuck_metrics['total_amount']})")
                health_status['overall_status'] = 'critical'
            elif stuck_metrics['count'] > 0:
                health_status['warnings'].append(f"Some stuck payments detected: {stuck_metrics['count']} (${stuck_metrics['total_amount']})")
                if health_status['overall_status'] == 'healthy':
                    health_status['overall_status'] = 'warning'
            
            # 2. Check webhook callback success rate
            webhook_metrics = await self._check_webhook_success_rate()
            health_status['metrics']['webhooks'] = webhook_metrics
            
            if webhook_metrics['success_rate'] < self.webhook_failure_threshold:
                health_status['issues'].append(f"Low webhook success rate: {webhook_metrics['success_rate']:.1%}")
                health_status['overall_status'] = 'critical'
            
            # 3. Check auth token storage
            auth_token_metrics = await self._check_auth_token_storage()
            health_status['metrics']['auth_tokens'] = auth_token_metrics
            
            if auth_token_metrics['missing_tokens'] > 0:
                health_status['issues'].append(f"Missing auth_tokens: {auth_token_metrics['missing_tokens']} payment intents")
                if health_status['overall_status'] != 'critical':
                    health_status['overall_status'] = 'warning'
            
            # 4. Check payment processing delays
            delay_metrics = await self._check_payment_delays()
            health_status['metrics']['delays'] = delay_metrics
            
            if delay_metrics['delayed_payments'] > 0:
                health_status['warnings'].append(f"Delayed payments: {delay_metrics['delayed_payments']}")
                if health_status['overall_status'] == 'healthy':
                    health_status['overall_status'] = 'warning'
            
            # 5. Check provider-specific issues
            provider_metrics = await self._check_provider_health()
            health_status['metrics']['providers'] = provider_metrics
            
            for provider, metrics in provider_metrics.items():
                if metrics.get('error_rate', 0) > 0.2:  # > 20% error rate
                    health_status['issues'].append(f"{provider} high error rate: {metrics['error_rate']:.1%}")
                    health_status['overall_status'] = 'critical'
            
            # Log health status
            status_emoji = "✅" if health_status['overall_status'] == 'healthy' else "⚠️" if health_status['overall_status'] == 'warning' else "🚨"
            logger.info(f"{status_emoji} Webhook system health: {health_status['overall_status'].upper()}")
            
            if health_status['issues']:
                logger.error(f"🚨 Critical issues: {', '.join(health_status['issues'])}")
            if health_status['warnings']:
                logger.warning(f"⚠️ Warnings: {', '.join(health_status['warnings'])}")
            
            return health_status
            
        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
            return {
                'timestamp': datetime.utcnow().isoformat(),
                'overall_status': 'error',
                'error': str(e)
            }
    
    async def _check_stuck_payments(self) -> Dict[str, Any]:
        """Check for stuck crypto payments"""
        try:
            result = await execute_query("""
                SELECT 
                    COUNT(*) as stuck_count,
                    COALESCE(SUM(amount), 0) as total_amount,
                    COUNT(CASE WHEN payment_provider = 'dynopay' THEN 1 END) as dynopay_stuck,
                    COUNT(CASE WHEN payment_provider = 'blockbee' THEN 1 END) as blockbee_stuck
                FROM payment_intents
                WHERE status IN ('address_created', 'created')
                  AND created_at >= NOW() - INTERVAL '7 days'
                  AND payment_address IS NOT NULL
            """)
            
            if result:
                return {
                    'count': result[0]['stuck_count'],
                    'total_amount': float(result[0]['total_amount']),
                    'by_provider': {
                        'dynopay': result[0]['dynopay_stuck'],
                        'blockbee': result[0]['blockbee_stuck']
                    }
                }
            
            return {'count': 0, 'total_amount': 0.0, 'by_provider': {}}
            
        except Exception as e:
            logger.error(f"❌ Error checking stuck payments: {e}")
            return {'count': -1, 'error': str(e)}
    
    async def _check_webhook_success_rate(self) -> Dict[str, Any]:
        """Check webhook processing success rate over last 24 hours"""
        try:
            # Get webhook callbacks from last 24 hours
            recent_webhooks = await execute_query("""
                SELECT 
                    COUNT(*) as total_callbacks,
                    COUNT(CASE WHEN status IN ('completed', 'confirmed') THEN 1 END) as successful,
                    COUNT(CASE WHEN status IN ('failed', 'error') THEN 1 END) as failed
                FROM webhook_callbacks
                WHERE created_at >= NOW() - INTERVAL '24 hours'
            """)
            
            if recent_webhooks and recent_webhooks[0]['total_callbacks'] > 0:
                total = recent_webhooks[0]['total_callbacks']
                successful = recent_webhooks[0]['successful']
                success_rate = successful / total
                
                return {
                    'total_callbacks': total,
                    'successful': successful,
                    'failed': recent_webhooks[0]['failed'],
                    'success_rate': success_rate
                }
            
            return {
                'total_callbacks': 0,
                'successful': 0,
                'failed': 0,
                'success_rate': 0.0,
                'note': 'No recent webhook callbacks found'
            }
            
        except Exception as e:
            logger.error(f"❌ Error checking webhook success rate: {e}")
            return {'error': str(e)}
    
    async def _check_auth_token_storage(self) -> Dict[str, Any]:
        """Check auth_token storage health"""
        try:
            result = await execute_query("""
                SELECT 
                    COUNT(*) as total_intents,
                    COUNT(CASE WHEN auth_token IS NULL THEN 1 END) as missing_tokens,
                    COUNT(CASE WHEN auth_token IS NOT NULL THEN 1 END) as has_tokens
                FROM payment_intents
                WHERE payment_provider = 'dynopay'
                  AND created_at >= NOW() - INTERVAL '24 hours'
            """)
            
            if result:
                return {
                    'total_intents': result[0]['total_intents'],
                    'missing_tokens': result[0]['missing_tokens'],
                    'has_tokens': result[0]['has_tokens'],
                    'token_storage_rate': result[0]['has_tokens'] / max(result[0]['total_intents'], 1)
                }
                
            return {'total_intents': 0, 'missing_tokens': 0, 'has_tokens': 0, 'token_storage_rate': 0.0}
            
        except Exception as e:
            logger.error(f"❌ Error checking auth token storage: {e}")
            return {'error': str(e)}
    
    async def _check_payment_delays(self) -> Dict[str, Any]:
        """Check for payment processing delays"""
        try:
            delay_threshold = datetime.utcnow() - timedelta(hours=self.payment_delay_threshold_hours)
            
            result = await execute_query("""
                SELECT COUNT(*) as delayed_payments
                FROM payment_intents
                WHERE status = 'address_created'
                  AND payment_address IS NOT NULL
                  AND created_at < %s
            """, (delay_threshold,))
            
            if result:
                return {
                    'delayed_payments': result[0]['delayed_payments'],
                    'threshold_hours': self.payment_delay_threshold_hours
                }
                
            return {'delayed_payments': 0}
            
        except Exception as e:
            logger.error(f"❌ Error checking payment delays: {e}")
            return {'error': str(e)}
    
    async def _check_provider_health(self) -> Dict[str, Any]:
        """Check individual payment provider health"""
        try:
            providers_health = {}
            
            # Check DynoPay
            dynopay_result = await execute_query("""
                SELECT 
                    COUNT(*) as total_attempts,
                    COUNT(CASE WHEN status IN ('confirmed', 'completed') THEN 1 END) as successful,
                    COUNT(CASE WHEN status IN ('failed', 'error') THEN 1 END) as failed
                FROM payment_intents
                WHERE payment_provider = 'dynopay'
                  AND created_at >= NOW() - INTERVAL '24 hours'
            """)
            
            if dynopay_result and dynopay_result[0]['total_attempts'] > 0:
                total = dynopay_result[0]['total_attempts']
                providers_health['dynopay'] = {
                    'total_attempts': total,
                    'successful': dynopay_result[0]['successful'],
                    'failed': dynopay_result[0]['failed'],
                    'success_rate': dynopay_result[0]['successful'] / total,
                    'error_rate': dynopay_result[0]['failed'] / total
                }
            
            # Check BlockBee  
            blockbee_result = await execute_query("""
                SELECT 
                    COUNT(*) as total_attempts,
                    COUNT(CASE WHEN status IN ('confirmed', 'completed') THEN 1 END) as successful,
                    COUNT(CASE WHEN status IN ('failed', 'error') THEN 1 END) as failed
                FROM payment_intents
                WHERE payment_provider = 'blockbee'
                  AND created_at >= NOW() - INTERVAL '24 hours'
            """)
            
            if blockbee_result and blockbee_result[0]['total_attempts'] > 0:
                total = blockbee_result[0]['total_attempts']
                providers_health['blockbee'] = {
                    'total_attempts': total,
                    'successful': blockbee_result[0]['successful'], 
                    'failed': blockbee_result[0]['failed'],
                    'success_rate': blockbee_result[0]['successful'] / total,
                    'error_rate': blockbee_result[0]['failed'] / total
                }
            
            return providers_health
            
        except Exception as e:
            logger.error(f"❌ Error checking provider health: {e}")
            return {'error': str(e)}
    
    async def continuous_monitor(self, interval_seconds: int = 300) -> None:
        """Run continuous monitoring with configurable interval"""
        try:
            logger.info(f"🔄 Starting continuous webhook monitoring (interval: {interval_seconds}s)...")
            
            while True:
                try:
                    health_status = await self.health_check()
                    
                    # Send alerts based on health status
                    if health_status['overall_status'] == 'critical':
                        await send_critical_alert(
                            "WebhookSystemCritical",
                            f"Critical webhook system issues detected: {', '.join(health_status['issues'])}",
                            "webhook_monitoring",
                            health_status
                        )
                    elif health_status['overall_status'] == 'warning':
                        await send_warning_alert(
                            "WebhookSystemWarning", 
                            f"Webhook system warnings: {', '.join(health_status.get('warnings', []))}",
                            "webhook_monitoring",
                            health_status
                        )
                    
                    # Log periodic status
                    if health_status['overall_status'] == 'healthy':
                        logger.info("✅ Webhook system running healthy")
                    
                except Exception as check_error:
                    logger.error(f"❌ Health check iteration failed: {check_error}")
                    await send_error_alert(
                        "WebhookMonitor",
                        f"Webhook monitoring system error: {check_error}", 
                        "monitoring_system"
                    )
                
                # Wait for next check
                await asyncio.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            logger.info("⚠️ Monitoring stopped by user")
        except Exception as e:
            logger.error(f"❌ Continuous monitoring failed: {e}")
            await send_critical_alert(
                "WebhookMonitorFailure",
                f"Webhook monitoring system crashed: {e}",
                "monitoring_system", 
                {"error": str(e)}
            )

async def main():
    """Main command line interface"""
    parser = argparse.ArgumentParser(description="Webhook Monitoring System")
    parser.add_argument('--health-check', action='store_true', help='Run one-time health check')
    parser.add_argument('--monitor', action='store_true', help='Run continuous monitoring')
    parser.add_argument('--interval', type=int, default=300, help='Monitoring interval in seconds (default: 300)')
    
    args = parser.parse_args()
    
    monitor = WebhookMonitor()
    
    try:
        if args.health_check:
            health_status = await monitor.health_check()
            
            print(f"\n🏥 WEBHOOK SYSTEM HEALTH CHECK")
            print("=" * 50)
            print(f"Status: {health_status['overall_status'].upper()}")
            print(f"Timestamp: {health_status['timestamp']}")
            
            if 'metrics' in health_status:
                print(f"\n📊 METRICS:")
                for category, metrics in health_status['metrics'].items():
                    print(f"  {category}: {metrics}")
            
            if health_status.get('issues'):
                print(f"\n🚨 CRITICAL ISSUES:")
                for issue in health_status['issues']:
                    print(f"  • {issue}")
            
            if health_status.get('warnings'):
                print(f"\n⚠️  WARNINGS:")
                for warning in health_status['warnings']:
                    print(f"  • {warning}")
                    
            if 'error' in health_status:
                print(f"\n❌ ERROR: {health_status['error']}")
                sys.exit(1)
            elif health_status['overall_status'] == 'critical':
                sys.exit(2)
            elif health_status['overall_status'] == 'warning':
                sys.exit(3)
        
        elif args.monitor:
            await monitor.continuous_monitor(args.interval)
        
        else:
            parser.print_help()
    
    except KeyboardInterrupt:
        print("\n⚠️ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Critical error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())