"""
Rate limiting service using sliding window algorithm.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from database import execute_query, execute_update

logger = logging.getLogger(__name__)


class RateLimitService:
    """Service for API rate limiting"""
    
    @staticmethod
    async def check_rate_limit(
        api_key_id: int,
        limit_per_hour: int,
        limit_per_day: int
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request is within rate limits.
        
        Args:
            api_key_id: API key ID
            limit_per_hour: Hourly limit
            limit_per_day: Daily limit
        
        Returns:
            Tuple of (is_allowed, stats_dict)
            stats_dict contains: remaining_hour, remaining_day, reset_time
        """
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)
        
        hour_count_result = await execute_query("""
            SELECT COUNT(*)
            FROM api_usage_logs
            WHERE api_key_id = %s AND created_at >= %s
        """, (api_key_id, hour_ago))
        
        day_count_result = await execute_query("""
            SELECT COUNT(*)
            FROM api_usage_logs
            WHERE api_key_id = %s AND created_at >= %s
        """, (api_key_id, day_ago))
        
        hour_count = hour_count_result[0][0] if hour_count_result else 0
        day_count = day_count_result[0][0] if day_count_result else 0
        
        remaining_hour = max(0, limit_per_hour - hour_count)
        remaining_day = max(0, limit_per_day - day_count)
        
        next_hour = int((now + timedelta(hours=1)).timestamp())
        
        stats = {
            "remaining_hour": remaining_hour,
            "remaining_day": remaining_day,
            "reset_time": next_hour,
            "limit_hour": limit_per_hour,
            "limit_day": limit_per_day
        }
        
        is_allowed = hour_count < limit_per_hour and day_count < limit_per_day
        
        if not is_allowed:
            if hour_count >= limit_per_hour:
                logger.warning(f"⚠️ Hourly rate limit exceeded for API key {api_key_id}: {hour_count}/{limit_per_hour}")
            if day_count >= limit_per_day:
                logger.warning(f"⚠️ Daily rate limit exceeded for API key {api_key_id}: {day_count}/{limit_per_day}")
        
        return is_allowed, stats
    
    @staticmethod
    async def log_request(
        api_key_id: int,
        endpoint: str,
        method: str,
        status_code: int,
        response_time_ms: int,
        request_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        error_message: Optional[str] = None,
        request_body_size: int = 0,
        response_body_size: int = 0
    ):
        """Log API request for usage tracking"""
        await execute_update("""
            INSERT INTO api_usage_logs (
                api_key_id, endpoint, method, status_code,
                response_time_ms, request_ip, user_agent,
                error_message, request_body_size, response_body_size
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            api_key_id, endpoint, method, status_code,
            response_time_ms, request_ip, user_agent,
            error_message, request_body_size, response_body_size
        ))
    
    @staticmethod
    async def get_usage_stats(
        api_key_id: int,
        hours: int = 24
    ) -> Dict[str, Any]:
        """Get usage statistics for an API key"""
        since = datetime.now() - timedelta(hours=hours)
        
        total_result = await execute_query("""
            SELECT COUNT(*) as count, AVG(response_time_ms) as avg_time
            FROM api_usage_logs
            WHERE api_key_id = %s AND created_at >= %s
        """, (api_key_id, since))
        
        by_status_result = await execute_query("""
            SELECT status_code, COUNT(*) as count
            FROM api_usage_logs
            WHERE api_key_id = %s AND created_at >= %s
            GROUP BY status_code
        """, (api_key_id, since))
        
        by_endpoint_result = await execute_query("""
            SELECT endpoint, COUNT(*) as count, AVG(response_time_ms) as avg_time
            FROM api_usage_logs
            WHERE api_key_id = %s AND created_at >= %s
            GROUP BY endpoint
            ORDER BY COUNT(*) DESC
            LIMIT 10
        """, (api_key_id, since))
        
        total_requests = total_result[0]['count'] if total_result else 0
        avg_response_time = float(total_result[0]['avg_time']) if total_result and total_result[0].get('avg_time') else 0
        
        status_breakdown = {}
        for row in by_status_result:
            status_breakdown[str(row['status_code'])] = row['count']
        
        top_endpoints = []
        for row in by_endpoint_result:
            top_endpoints.append({
                "endpoint": row['endpoint'],
                "requests": row['count'],
                "avg_response_time_ms": float(row['avg_time']) if row.get('avg_time') else 0
            })
        
        return {
            "period_hours": hours,
            "total_requests": total_requests,
            "avg_response_time_ms": round(avg_response_time, 2),
            "status_breakdown": status_breakdown,
            "top_endpoints": top_endpoints
        }
