"""
Maintenance Manager Service for Telegram Bot
Manages system-wide maintenance mode with singleton pattern
"""

import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
from database import execute_query, execute_update

logger = logging.getLogger(__name__)

class MaintenanceManager:
    """
    Manages system maintenance mode with singleton pattern.
    Provides methods to enable/disable maintenance and check status.
    """
    
    @staticmethod
    async def is_maintenance_active() -> bool:
        """
        Check if maintenance mode is currently active.
        
        Returns:
            bool: True if maintenance is active, False otherwise
        """
        try:
            result = await execute_query(
                "SELECT is_active FROM system_maintenance LIMIT 1",
                ()
            )
            
            if result and len(result) > 0:
                return bool(result[0].get('is_active', False))
            
            return False
            
        except Exception as e:
            logger.error(f"❌ MAINTENANCE: Error checking maintenance status: {e}")
            return False
    
    @staticmethod
    async def get_maintenance_status() -> Dict:
        """
        Get detailed maintenance status including timing information.
        
        Returns:
            Dict containing:
                - is_active: bool
                - started_at: datetime or None
                - ends_at: datetime or None
                - duration_minutes: int or None
                - time_remaining_seconds: int or None
        """
        try:
            result = await execute_query(
                """
                SELECT is_active, started_at, ends_at, duration_minutes, created_by
                FROM system_maintenance 
                LIMIT 1
                """,
                ()
            )
            
            if not result or len(result) == 0:
                return {
                    'is_active': False,
                    'started_at': None,
                    'ends_at': None,
                    'duration_minutes': None,
                    'time_remaining_seconds': None,
                    'created_by': None
                }
            
            record = result[0]
            is_active = bool(record.get('is_active', False))
            started_at = record.get('started_at')
            ends_at = record.get('ends_at')
            duration_minutes = record.get('duration_minutes')
            created_by = record.get('created_by')
            
            time_remaining_seconds = None
            if is_active and ends_at:
                now = datetime.now(ends_at.tzinfo) if ends_at.tzinfo else datetime.now()
                delta = ends_at - now
                time_remaining_seconds = max(0, int(delta.total_seconds()))
            
            return {
                'is_active': is_active,
                'started_at': started_at,
                'ends_at': ends_at,
                'duration_minutes': duration_minutes,
                'time_remaining_seconds': time_remaining_seconds,
                'created_by': created_by
            }
            
        except Exception as e:
            logger.error(f"❌ MAINTENANCE: Error getting maintenance status: {e}")
            return {
                'is_active': False,
                'started_at': None,
                'ends_at': None,
                'duration_minutes': None,
                'time_remaining_seconds': None,
                'created_by': None
            }
    
    @staticmethod
    async def enable_maintenance(admin_user_id: int, duration_minutes: int) -> bool:
        """
        Enable maintenance mode for specified duration.
        
        Args:
            admin_user_id: Internal user ID of the admin enabling maintenance
            duration_minutes: Duration of maintenance in minutes
            
        Returns:
            bool: True if successfully enabled, False otherwise
        """
        try:
            now = datetime.now()
            ends_at = now + timedelta(minutes=duration_minutes)
            
            await execute_update(
                """
                UPDATE system_maintenance
                SET is_active = true,
                    started_at = %s,
                    ends_at = %s,
                    duration_minutes = %s,
                    created_by = %s,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (now, ends_at, duration_minutes, admin_user_id)
            )
            
            logger.info(
                f"🔧 MAINTENANCE: Enabled by admin {admin_user_id} "
                f"for {duration_minutes} minutes (until {ends_at})"
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ MAINTENANCE: Error enabling maintenance: {e}")
            return False
    
    @staticmethod
    async def disable_maintenance() -> bool:
        """
        Disable maintenance mode.
        
        Returns:
            bool: True if successfully disabled, False otherwise
        """
        try:
            await execute_update(
                """
                UPDATE system_maintenance
                SET is_active = false,
                    started_at = NULL,
                    ends_at = NULL,
                    duration_minutes = NULL,
                    updated_at = CURRENT_TIMESTAMP
                """,
                ()
            )
            
            logger.info("✅ MAINTENANCE: Maintenance mode disabled")
            return True
            
        except Exception as e:
            logger.error(f"❌ MAINTENANCE: Error disabling maintenance: {e}")
            return False
    
    @staticmethod
    async def get_maintenance_message(language: str = 'en') -> str:
        """
        Get formatted maintenance message with countdown or status.
        
        Args:
            language: Language code for localized message
            
        Returns:
            str: Formatted maintenance message
        """
        try:
            status = await MaintenanceManager.get_maintenance_status()
            
            if not status['is_active']:
                return "Maintenance mode is not active."
            
            time_remaining = status.get('time_remaining_seconds')
            
            if time_remaining is None:
                message = "🔧 <b>System Maintenance</b>\n\n"
                message += "The system is currently undergoing maintenance.\n"
                message += "Please try again later."
            elif time_remaining > 0:
                minutes = time_remaining // 60
                seconds = time_remaining % 60
                message = "🔧 <b>System Maintenance</b>\n\n"
                message += "The system is currently undergoing maintenance.\n\n"
                message += f"⏳ <b>Time remaining:</b> {minutes} min {seconds} sec\n\n"
                message += "Please try again after maintenance is complete."
            else:
                message = "🔧 <b>System Maintenance</b>\n\n"
                message += "The system is currently undergoing maintenance.\n\n"
                message += "✅ Maintenance should be completing soon!\n\n"
                message += "Please try again in a moment."
            
            return message
            
        except Exception as e:
            logger.error(f"❌ MAINTENANCE: Error getting maintenance message: {e}")
            return "🔧 <b>System Maintenance</b>\n\nThe system is currently undergoing maintenance. Please try again later."
