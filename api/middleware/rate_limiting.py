"""
Rate limiting middleware.
"""
import logging
from fastapi import Request, Response
from api.services.rate_limit_service import RateLimitService
from api.utils.errors import RateLimitExceededError

logger = logging.getLogger(__name__)


async def check_rate_limit(request: Request, key_data: dict) -> dict:
    """
    Check rate limits for API key.
    
    Args:
        request: FastAPI request object
        key_data: API key data dictionary
    
    Returns:
        Rate limit statistics
    
    Raises:
        RateLimitExceededError: If rate limit is exceeded
    """
    api_key_id = key_data["id"]
    limit_per_hour = key_data.get("rate_limit_per_hour", 1000)
    limit_per_day = key_data.get("rate_limit_per_day", 10000)
    
    is_allowed, stats = await RateLimitService.check_rate_limit(
        api_key_id,
        limit_per_hour,
        limit_per_day
    )
    
    if not is_allowed:
        retry_after = 3600
        raise RateLimitExceededError(
            retry_after=retry_after,
            details={
                "limit_hour": stats["limit_hour"],
                "limit_day": stats["limit_day"],
                "remaining_hour": stats["remaining_hour"],
                "remaining_day": stats["remaining_day"]
            }
        )
    
    return stats


def add_rate_limit_headers(response: Response, stats: dict):
    """
    Add rate limit headers to response.
    
    Args:
        response: FastAPI response object
        stats: Rate limit statistics
    """
    response.headers["X-RateLimit-Limit-Hour"] = str(stats.get("limit_hour", 1000))
    response.headers["X-RateLimit-Limit-Day"] = str(stats.get("limit_day", 10000))
    response.headers["X-RateLimit-Remaining-Hour"] = str(stats.get("remaining_hour", 0))
    response.headers["X-RateLimit-Remaining-Day"] = str(stats.get("remaining_day", 0))
    response.headers["X-RateLimit-Reset"] = str(stats.get("reset_time", 0))
