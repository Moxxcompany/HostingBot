"""
Comprehensive Admin Alert System for HostBay Telegram Bot

This module provides a centralized admin notification system for critical issues
with rate limiting, severity levels, and integration with the existing bot infrastructure.

Features:
- Multiple severity levels (CRITICAL, ERROR, WARNING)
- Rate limiting to prevent alert spam
- Alert suppression for duplicate alerts
- Integration with existing ADMIN_USER_ID environment variable
- Support for multiple admin users
- Structured alert data with categorization
- Telegram message formatting for readability
"""

import os
import logging
import time
import hashlib
import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Any, Union
from enum import Enum
from decimal import Decimal
from dataclasses import dataclass, asdict
from database import execute_query, execute_update

logger = logging.getLogger(__name__)

# ====================================================================
# USER INFO CACHE FOR USERNAME LOOKUPS
# ====================================================================

_username_cache: Dict[int, Optional[str]] = {}
_cache_expiry: Dict[int, float] = {}
USERNAME_CACHE_TTL = 300  # 5 minutes

async def get_username_for_alert(user_id: int) -> Optional[str]:
    """
    Fetch username for a user_id to include in admin alerts.
    Uses caching to avoid repeated database queries.
    
    Returns:
        Username string (with @ prefix) or None if not available
    """
    if not user_id:
        return None
    
    # Check cache first
    now = time.time()
    if user_id in _username_cache and _cache_expiry.get(user_id, 0) > now:
        return _username_cache[user_id]
    
    try:
        result = await execute_query(
            "SELECT username, first_name FROM users WHERE id = %s LIMIT 1",
            (user_id,)
        )
        
        if result and len(result) > 0:
            username = result[0].get('username')
            first_name = result[0].get('first_name')
            
            # Format username with @ or use first_name as fallback
            if username:
                formatted = f"@{username}"
            elif first_name:
                formatted = first_name
            else:
                formatted = None
            
            # Cache the result
            _username_cache[user_id] = formatted
            _cache_expiry[user_id] = now + USERNAME_CACHE_TTL
            
            return formatted
        
        return None
        
    except Exception as e:
        logger.debug(f"Could not fetch username for user_id {user_id}: {e}")
        return None

async def get_username_by_telegram_id(telegram_id: int) -> Optional[str]:
    """
    Fetch username by telegram_id for admin alerts.
    
    Returns:
        Username string (with @ prefix) or None if not available
    """
    if not telegram_id:
        return None
    
    try:
        result = await execute_query(
            "SELECT username, first_name FROM users WHERE telegram_id = %s LIMIT 1",
            (telegram_id,)
        )
        
        if result and len(result) > 0:
            username = result[0].get('username')
            first_name = result[0].get('first_name')
            
            if username:
                return f"@{username}"
            elif first_name:
                return first_name
        
        return None
        
    except Exception as e:
        logger.debug(f"Could not fetch username for telegram_id {telegram_id}: {e}")
        return None

# ====================================================================
# JSON ENCODER FOR ADMIN ALERTS
# ====================================================================

class AdminAlertEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles Decimal, datetime, and Enum types"""
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (datetime,)):
            return o.isoformat()
        if isinstance(o, Enum):
            return o.value
        return super().default(o)

# ====================================================================
# ALERT SEVERITY LEVELS AND CONFIGURATION
# ====================================================================

class AlertSeverity(Enum):
    """Alert severity levels"""
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"

class AlertCategory(Enum):
    """Alert categories for filtering and organization"""
    DOMAIN_REGISTRATION = "domain_registration"
    PAYMENT_PROCESSING = "payment_processing"
    SYSTEM_HEALTH = "system_health"
    SECURITY = "security"
    EXTERNAL_API = "external_api"
    DATABASE = "database"
    WEBHOOK = "webhook"
    HOSTING = "hosting"

@dataclass
class Alert:
    """Structured alert data"""
    severity: AlertSeverity
    category: AlertCategory
    component: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None
    fingerprint: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
        if self.fingerprint is None:
            self.fingerprint = self._generate_fingerprint()
    
    def _generate_fingerprint(self) -> str:
        """Generate a unique fingerprint for alert deduplication"""
        content = f"{self.severity.value}:{self.category.value}:{self.component}:{self.message}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary for storage"""
        data = asdict(self)
        data['severity'] = self.severity.value
        data['category'] = self.category.value
        data['timestamp'] = self.timestamp.isoformat() if self.timestamp else None
        return data

# ====================================================================
# ADMIN ALERT CONFIGURATION
# ====================================================================

class AdminAlertConfig:
    """Configuration for admin alert system"""
    
    def __init__(self):
        # Rate limiting settings
        self.rate_limit_window = int(os.getenv('ALERT_RATE_LIMIT_WINDOW', '300'))  # 5 minutes
        self.max_alerts_per_window = int(os.getenv('ALERT_MAX_PER_WINDOW', '10'))
        
        # Alert suppression settings
        self.suppression_window = int(os.getenv('ALERT_SUPPRESSION_WINDOW', '3600'))  # 1 hour
        
        # Admin user configuration
        self.admin_user_ids = self._parse_admin_users()
        
        # Alert level filtering (default to INFO to receive all notifications)
        self.min_severity = AlertSeverity(os.getenv('ALERT_MIN_SEVERITY', 'INFO'))
        
        # Enable/disable alerts
        self.alerts_enabled = os.getenv('ADMIN_ALERTS_ENABLED', 'true').lower() == 'true'
        
        logger.info(f"✅ Admin Alert Config: enabled={self.alerts_enabled}, "
                   f"admins={len(self.admin_user_ids)}, min_severity={self.min_severity.value}")
    
    def _parse_admin_users(self) -> List[int]:
        """Parse admin user IDs from environment variables"""
        admin_ids = []
        
        # Try the standard ADMIN_USER_IDS first (comma-separated)
        admin_ids_str = os.getenv('ADMIN_USER_IDS', '')
        if admin_ids_str:
            for admin_id in admin_ids_str.split(','):
                admin_id = admin_id.strip()
                if admin_id:
                    try:
                        admin_ids.append(int(admin_id))
                    except ValueError:
                        logger.warning(f"Invalid ADMIN_USER_IDS format: {admin_id}")
        
        # Fallback to legacy format for backward compatibility
        if not admin_ids:
            # Primary admin user
            primary_admin = os.getenv('ADMIN_USER_ID')
            if primary_admin:
                try:
                    admin_ids.append(int(primary_admin))
                except ValueError:
                    logger.warning(f"Invalid ADMIN_USER_ID format: {primary_admin}")
            
            # Additional admin users (comma-separated)
            additional_admins = os.getenv('ADDITIONAL_ADMIN_USER_IDS', '')
            if additional_admins:
                for admin_id in additional_admins.split(','):
                    admin_id = admin_id.strip()
                    if admin_id:
                        try:
                            admin_ids.append(int(admin_id))
                        except ValueError:
                            logger.warning(f"Invalid additional admin ID format: {admin_id}")
        
        if not admin_ids:
            logger.warning("⚠️ No admin user IDs configured - alerts will be logged only")
        
        return admin_ids

# ====================================================================
# ADMIN ALERT SYSTEM - MAIN CLASS
# ====================================================================

class AdminAlertSystem:
    """Main admin alert system with rate limiting and deduplication"""
    
    def __init__(self):
        self.config = AdminAlertConfig()
        self._alert_history: List[Dict[str, Any]] = []
        self._suppressed_alerts: Dict[str, datetime] = {}
        self._rate_limit_tracker: List[datetime] = []
        self._bot_application = None
        self._bot_loop = None
        
        # Initialize database table for alert persistence (lazy initialization)
        self._storage_initialized = False
    
    async def _init_alert_storage(self):
        """Initialize database table for alert storage"""
        try:
            await execute_update("""
                CREATE TABLE IF NOT EXISTS admin_alerts (
                    id SERIAL PRIMARY KEY,
                    severity VARCHAR(20) NOT NULL,
                    category VARCHAR(50) NOT NULL,
                    component VARCHAR(100) NOT NULL,
                    message TEXT NOT NULL,
                    details JSONB,
                    fingerprint VARCHAR(32) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sent_at TIMESTAMP,
                    suppressed BOOLEAN DEFAULT FALSE
                )
            """)
            
            # Create index on fingerprint for deduplication
            await execute_update("""
                CREATE INDEX IF NOT EXISTS idx_admin_alerts_fingerprint 
                ON admin_alerts(fingerprint)
            """)
            
            # Create index on created_at for cleanup
            await execute_update("""
                CREATE INDEX IF NOT EXISTS idx_admin_alerts_created_at 
                ON admin_alerts(created_at)
            """)
            
            logger.info("✅ Admin alert storage initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize admin alert storage: {e}")
    
    def set_bot_application(self, application, loop=None):
        """Set the bot application for sending alerts"""
        self._bot_application = application
        self._bot_loop = loop
        logger.info("✅ Bot application set for admin alerts")
    
    def _is_rate_limited(self) -> bool:
        """Check if we're currently rate limited"""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.config.rate_limit_window)
        
        # Clean old entries
        self._rate_limit_tracker = [ts for ts in self._rate_limit_tracker if ts > cutoff]
        
        # Check if we've exceeded the limit
        return len(self._rate_limit_tracker) >= self.config.max_alerts_per_window
    
    def _is_suppressed(self, fingerprint: str) -> bool:
        """Check if an alert is currently suppressed"""
        if fingerprint not in self._suppressed_alerts:
            return False
        
        suppressed_until = self._suppressed_alerts[fingerprint]
        if datetime.now(timezone.utc) > suppressed_until:
            del self._suppressed_alerts[fingerprint]
            return False
        
        return True
    
    def _suppress_alert(self, fingerprint: str):
        """Suppress an alert for the configured window"""
        suppression_time = datetime.now(timezone.utc) + timedelta(seconds=self.config.suppression_window)
        self._suppressed_alerts[fingerprint] = suppression_time
    
    def _format_alert_message(self, alert: Alert, username: Optional[str] = None) -> str:
        """Format alert for Telegram message with optional username display"""
        # Severity icon mapping
        severity_icons = {
            AlertSeverity.CRITICAL: "🔴",
            AlertSeverity.ERROR: "🟠", 
            AlertSeverity.WARNING: "🟡",
            AlertSeverity.INFO: "🔵"
        }
        
        # Category icon mapping
        category_icons = {
            AlertCategory.DOMAIN_REGISTRATION: "🌐",
            AlertCategory.PAYMENT_PROCESSING: "💰",
            AlertCategory.SYSTEM_HEALTH: "🏥",
            AlertCategory.SECURITY: "🛡️",
            AlertCategory.EXTERNAL_API: "🔗",
            AlertCategory.DATABASE: "🗄️",
            AlertCategory.WEBHOOK: "📡",
            AlertCategory.HOSTING: "🖥️"
        }
        
        icon = severity_icons.get(alert.severity, "⚠️")
        cat_icon = category_icons.get(alert.category, "📋")
        
        # Format timestamp
        timestamp_str = alert.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC") if alert.timestamp else "Unknown"
        
        # Build message
        message_parts = [
            f"{icon} <b>ADMIN ALERT - {alert.severity.value}</b>",
            f"{cat_icon} <b>Category:</b> {alert.category.value.replace('_', ' ').title()}",
            f"🔧 <b>Component:</b> {alert.component}",
            f"📝 <b>Message:</b> {alert.message}",
            f"🕐 <b>Time:</b> {timestamp_str}",
        ]
        
        # Add customer username prominently if available
        if username:
            message_parts.insert(4, f"👤 <b>Customer:</b> {username}")
        
        # Add details if present
        if alert.details:
            message_parts.append(f"📊 <b>Details:</b>")
            for key, value in alert.details.items():
                # Skip customer field if already shown prominently
                if key == 'customer':
                    continue
                if isinstance(value, dict):
                    value = json.dumps(value, indent=2)
                elif isinstance(value, (list, tuple)):
                    value = ", ".join(str(v) for v in value)
                message_parts.append(f"   • <b>{key}:</b> {value}")
        
        return "\n".join(message_parts)
    
    async def _send_alert_to_admin(self, admin_id: int, alert: Alert, username: Optional[str] = None) -> bool:
        """Send alert to a specific admin user"""
        if not self._bot_application:
            # Enhanced fallback with comprehensive auto-connection
            logger.info("🔄 ADMIN ALERTS: Bot application not connected, attempting auto-connection...")
            _auto_connect_bot_application(self)
            
            if not self._bot_application:
                logger.warning("📞 ADMIN ALERTS: No bot application available after auto-connection, alert delivery skipped")
                return False
        
        if not self._bot_application.bot:
            logger.warning("⚠️ Bot application initialized but bot instance not available for admin alerts")
            return False
        
        try:
            message = self._format_alert_message(alert, username)
            logger.debug(f"🔧 ADMIN ALERTS: Sending message to {admin_id}: {message[:100]}...")
            
            # CRITICAL FIX: Always send directly in async context (no threading)
            try:
                await self._bot_application.bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode='HTML'
                )
                logger.info(f"✅ Admin alert sent to {admin_id}: {alert.severity.value} - {alert.component}")
                return True
                
            except Exception as send_error:
                logger.error(f"❌ Telegram send failed for {admin_id}: {send_error}")
                # Try without HTML parsing as fallback
                try:
                    await self._bot_application.bot.send_message(
                        chat_id=admin_id,
                        text=message.replace('<b>', '').replace('</b>', ''),
                        parse_mode=None
                    )
                    logger.info(f"✅ Admin alert sent to {admin_id} (plain text fallback): {alert.component}")
                    return True
                except Exception as fallback_error:
                    logger.error(f"❌ Plain text fallback also failed for {admin_id}: {fallback_error}")
                    return False
            
        except Exception as e:
            logger.error(f"❌ Failed to send admin alert to {admin_id}: {str(e)}")
            return False
    
    async def _store_alert(self, alert: Alert, sent: bool) -> bool:
        """Store alert in database"""
        try:
            await execute_update("""
                INSERT INTO admin_alerts 
                (id, severity, category, component, message, details, fingerprint, sent_at, suppressed)
                VALUES (DEFAULT, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                alert.severity.value,
                alert.category.value,
                alert.component,
                alert.message,
                json.dumps(alert.details, cls=AdminAlertEncoder) if alert.details else None,
                alert.fingerprint,
                alert.timestamp if sent else None,
                not sent
            ))
            return True
        except Exception as e:
            logger.error(f"❌ Failed to store admin alert: {e}")
            return False
    
    async def send_alert(
        self,
        severity: Union[AlertSeverity, str],
        category: Union[AlertCategory, str],
        component: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send an admin alert with rate limiting and deduplication
        
        Args:
            severity: Alert severity level
            category: Alert category
            component: Component that generated the alert
            message: Human-readable alert message
            details: Additional structured data
            
        Returns:
            bool: True if alert was sent successfully
        """
        try:
            # Ensure storage is initialized (lazy initialization)
            if not self._storage_initialized:
                await self._init_alert_storage()
                self._storage_initialized = True
            
            # Check if alerts are enabled
            if not self.config.alerts_enabled:
                logger.debug(f"Admin alerts disabled - skipping: {component}: {message}")
                return False
            
            # Convert string enums to enum objects
            if isinstance(severity, str):
                severity = AlertSeverity(severity.upper())
            if isinstance(category, str):
                category = AlertCategory(category.lower())
            
            # Check minimum severity
            severity_order = [AlertSeverity.INFO, AlertSeverity.WARNING, AlertSeverity.ERROR, AlertSeverity.CRITICAL]
            if severity_order.index(severity) < severity_order.index(self.config.min_severity):
                logger.debug(f"Alert below minimum severity ({self.config.min_severity.value}) - skipping: {message}")
                return False
            
            # Create alert object
            alert = Alert(
                severity=severity,
                category=category,
                component=component,
                message=message,
                details=details
            )
            
            # Check for suppression (duplicate alerts)
            if alert.fingerprint and self._is_suppressed(alert.fingerprint):
                logger.debug(f"Alert suppressed (duplicate): {component}: {message}")
                await self._store_alert(alert, sent=False)
                return False
            
            # Check rate limiting
            if self._is_rate_limited():
                logger.warning(f"⚠️ Admin alerts rate limited - dropping: {component}: {message}")
                await self._store_alert(alert, sent=False)
                return False
            
            # Look up username from details if user_id is present
            username = None
            if details:
                user_id = details.get('user_id')
                telegram_id = details.get('telegram_id')
                
                # Try to get username from user_id first, then telegram_id
                if user_id:
                    try:
                        username = await get_username_for_alert(int(user_id))
                    except (ValueError, TypeError):
                        pass
                
                if not username and telegram_id:
                    try:
                        username = await get_username_by_telegram_id(int(telegram_id))
                    except (ValueError, TypeError):
                        pass
            
            # Send to all configured admin users
            sent_count = 0
            for admin_id in self.config.admin_user_ids:
                if await self._send_alert_to_admin(admin_id, alert, username):
                    sent_count += 1
            
            # Update tracking
            if sent_count > 0:
                self._rate_limit_tracker.append(datetime.now(timezone.utc))
                if alert.fingerprint:
                    self._suppress_alert(alert.fingerprint)
                await self._store_alert(alert, sent=True)
                
                # Also log to application logs
                log_level = getattr(logging, severity.value.upper(), logging.WARNING)
                logger.log(log_level, f"🚨 ADMIN ALERT ({severity.value}): [{component}] {message}")
                
                return True
            else:
                # Failed to send to any admin
                logger.error(f"❌ Failed to send admin alert to any admin: {component}: {message}")
                await self._store_alert(alert, sent=False)
                return False
                
        except Exception as e:
            logger.error(f"❌ Admin alert system error: {e}")
            # Still log the original alert message
            logger.error(f"🚨 ALERT (failed to send): [{component}] {message}")
            return False
    
    async def cleanup_old_alerts(self, days_old: int = 30) -> int:
        """Clean up old alerts from database"""
        try:
            # Use UTC time calculation to avoid timezone issues
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=days_old)
            result = await execute_update("""
                DELETE FROM admin_alerts 
                WHERE created_at < %s
            """, (cutoff_time,))
            
            cleaned_count = result if result else 0
            if cleaned_count > 0:
                logger.info(f"🧹 Cleaned up {cleaned_count} old admin alerts")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"❌ Failed to cleanup old admin alerts: {e}")
            return 0
    
    async def get_alert_stats(self) -> Dict[str, Any]:
        """Get statistics about admin alerts"""
        try:
            # Get recent alert counts by severity (use UTC time for consistency)
            cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
            recent_alerts = await execute_query("""
                SELECT severity, COUNT(*) as count
                FROM admin_alerts 
                WHERE created_at > %s
                GROUP BY severity
            """, (cutoff_24h,))
            
            # Get suppressed alert count
            suppressed_count = await execute_query("""
                SELECT COUNT(*) as count
                FROM admin_alerts 
                WHERE suppressed = true 
                AND created_at > %s
            """, (cutoff_24h,))
            
            stats = {
                'enabled': self.config.alerts_enabled,
                'admin_count': len(self.config.admin_user_ids),
                'rate_limit_window': self.config.rate_limit_window,
                'max_alerts_per_window': self.config.max_alerts_per_window,
                'min_severity': self.config.min_severity.value,
                'recent_24h': {row['severity']: row['count'] for row in recent_alerts},
                'suppressed_24h': suppressed_count[0]['count'] if suppressed_count else 0,
                'currently_suppressed': len(self._suppressed_alerts)
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Failed to get alert stats: {e}")
            return {'error': str(e)}

# ====================================================================
# GLOBAL ADMIN ALERT INSTANCE
# ====================================================================

# Global instance for easy access across the application
_admin_alert_system = None

def get_admin_alert_system() -> AdminAlertSystem:
    """Get or create the global admin alert system instance"""
    global _admin_alert_system
    if _admin_alert_system is None:
        _admin_alert_system = AdminAlertSystem()
        logger.info("✅ Admin alert system initialized")
        # CRITICAL FIX: Auto-connect bot application if available
        _auto_connect_bot_application(_admin_alert_system)
    return _admin_alert_system

def _auto_connect_bot_application(alert_system: AdminAlertSystem):
    """Automatically connect bot application from available sources"""
    if alert_system._bot_application:
        return  # Already connected
    
    try:
        # Try multiple sources for bot application
        bot_app = None
        
        # Source 1: Global builtins storage
        try:
            import builtins
            bot_app = getattr(builtins, '_global_bot_application', None)
            if bot_app:
                logger.info("🔄 ADMIN ALERTS: Auto-connected via global storage")
        except Exception:
            pass
        
        # Source 2: Webhook handler
        if not bot_app:
            try:
                from webhook_handler import get_bot_application
                bot_app = get_bot_application()
                if bot_app:
                    logger.info("🔄 ADMIN ALERTS: Auto-connected via webhook handler")
            except Exception:
                pass
        
        # Source 3: Direct fastapi_server access (if running)
        if not bot_app:
            try:
                import sys
                if 'fastapi_server' in sys.modules:
                    fastapi_server = sys.modules['fastapi_server']
                    if hasattr(fastapi_server, '_bot_application_instance'):
                        bot_app = fastapi_server._bot_application_instance
                        logger.info("🔄 ADMIN ALERTS: Auto-connected via fastapi_server")
            except Exception:
                pass
        
        if bot_app:
            alert_system.set_bot_application(bot_app)
            logger.info("✅ ADMIN ALERTS: Auto-connection successful")
        else:
            logger.debug("📞 ADMIN ALERTS: No bot application available for auto-connection")
            
    except Exception as e:
        logger.debug(f"📞 ADMIN ALERTS: Auto-connection failed: {e}")

def set_admin_alert_bot_application(application, loop=None):
    """Set the bot application for the global admin alert system"""
    alert_system = get_admin_alert_system()
    alert_system.set_bot_application(application, loop)

# ====================================================================
# CONVENIENCE FUNCTIONS FOR EASY INTEGRATION
# ====================================================================

async def send_critical_alert(component: str, message: str, category: str = "system_health", details: Optional[Dict[str, Any]] = None):
    """Send a critical admin alert"""
    alert_system = get_admin_alert_system()
    return await alert_system.send_alert(AlertSeverity.CRITICAL, category, component, message, details)

async def send_error_alert(component: str, message: str, category: str = "system_health", details: Optional[Dict[str, Any]] = None):
    """Send an error admin alert"""
    alert_system = get_admin_alert_system()
    return await alert_system.send_alert(AlertSeverity.ERROR, category, component, message, details)

async def send_warning_alert(component: str, message: str, category: str = "system_health", details: Optional[Dict[str, Any]] = None):
    """Send a warning admin alert"""
    alert_system = get_admin_alert_system()
    return await alert_system.send_alert(AlertSeverity.WARNING, category, component, message, details)

async def send_info_alert(component: str, message: str, category: str = "system_health", details: Optional[Dict[str, Any]] = None):
    """Send an info admin alert"""
    alert_system = get_admin_alert_system()
    return await alert_system.send_alert(AlertSeverity.INFO, category, component, message, details)

# ====================================================================
# TESTING AND VERIFICATION FUNCTIONS
# ====================================================================

async def test_admin_alerts() -> Dict[str, Any]:
    """Test the admin alert system functionality"""
    alert_system = get_admin_alert_system()
    
    test_results = {
        'config_test': False,
        'rate_limit_test': False,
        'suppression_test': False,
        'send_test': False,
        'errors': []
    }
    
    try:
        # Test 1: Configuration validation
        if alert_system.config.admin_user_ids:
            test_results['config_test'] = True
        else:
            test_results['errors'].append("No admin users configured")
        
        # Test 2: Send test alert
        test_sent = await alert_system.send_alert(
            AlertSeverity.INFO,
            AlertCategory.SYSTEM_HEALTH,
            "AdminAlertSystem",
            "Test alert - system verification",
            {"test": True, "timestamp": datetime.now(timezone.utc).isoformat()}
        )
        test_results['send_test'] = test_sent
        
        # Test 3: Suppression test (send same alert twice)
        first_send = await alert_system.send_alert(
            AlertSeverity.WARNING,
            AlertCategory.SYSTEM_HEALTH,
            "AdminAlertSystem",
            "Duplicate test alert",
            {"test": "suppression"}
        )
        
        second_send = await alert_system.send_alert(
            AlertSeverity.WARNING,
            AlertCategory.SYSTEM_HEALTH,
            "AdminAlertSystem",
            "Duplicate test alert",
            {"test": "suppression"}
        )
        
        test_results['suppression_test'] = first_send and not second_send
        
        # Test 4: Rate limiting (send many alerts rapidly)
        rate_limit_triggered = False
        for i in range(alert_system.config.max_alerts_per_window + 5):
            result = await alert_system.send_alert(
                AlertSeverity.INFO,
                AlertCategory.SYSTEM_HEALTH,
                "AdminAlertSystem",
                f"Rate limit test {i}",
                {"test": "rate_limit", "number": i}
            )
            if not result:
                rate_limit_triggered = True
                break
        
        test_results['rate_limit_test'] = rate_limit_triggered
        
        logger.info(f"✅ Admin alert system test completed: {test_results}")
        return test_results
        
    except Exception as e:
        test_results['errors'].append(str(e))
        logger.error(f"❌ Admin alert system test failed: {e}")
        return test_results

if __name__ == "__main__":
    # Direct testing when run as script
    import asyncio
    
    async def main():
        print("Testing Admin Alert System...")
        results = await test_admin_alerts()
        print(f"Test Results: {results}")
    
    asyncio.run(main())