"""
Custom exceptions and error handling for API.
"""
from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class APIError(HTTPException):
    """Base API error"""
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        self.error_code = error_code
        self.details = details or {}
        super().__init__(
            status_code=status_code,
            detail={
                "error": {
                    "code": error_code,
                    "message": message,
                    "details": self.details
                }
            }
        )


class AuthenticationError(APIError):
    """Authentication failed"""
    def __init__(self, message: str = "Invalid or missing API key", details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTHENTICATION_FAILED",
            message=message,
            details=details
        )


class PermissionDeniedError(APIError):
    """Permission denied"""
    def __init__(self, message: str = "Permission denied", details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="PERMISSION_DENIED",
            message=message,
            details=details
        )


class RateLimitExceededError(APIError):
    """Rate limit exceeded"""
    def __init__(self, retry_after: int, details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="RATE_LIMIT_EXCEEDED",
            message=f"Rate limit exceeded. Retry after {retry_after} seconds",
            details={"retry_after": retry_after, **(details or {})}
        )


class ResourceNotFoundError(APIError):
    """Resource not found"""
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="RESOURCE_NOT_FOUND",
            message=f"{resource} not found",
            details={"resource": resource, "identifier": identifier}
        )


class BadRequestError(APIError):
    """Bad request"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="BAD_REQUEST",
            message=message,
            details=details
        )


class ValidationError(APIError):
    """Input validation failed"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            message=message,
            details=details
        )


class ConflictError(APIError):
    """Resource conflict"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            error_code="CONFLICT",
            message=message,
            details=details
        )


class InternalServerError(APIError):
    """Internal server error"""
    def __init__(self, message: str = "An internal error occurred", details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="INTERNAL_ERROR",
            message=message,
            details=details
        )
