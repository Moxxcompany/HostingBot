"""
Common schemas used across API.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Error detail schema"""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Standard error response"""
    success: bool = False
    error: ErrorDetail


class SuccessResponse(BaseModel):
    """Standard success response"""
    success: bool = True
    data: Any
    message: Optional[str] = None


class PaginationParams(BaseModel):
    """Pagination query parameters"""
    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    per_page: int = Field(50, ge=1, le=100, description="Items per page (max 100)")


class PaginationMeta(BaseModel):
    """Pagination metadata"""
    page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class PaginatedResponse(BaseModel):
    """Paginated list response"""
    success: bool = True
    data: List[Any]
    pagination: PaginationMeta
