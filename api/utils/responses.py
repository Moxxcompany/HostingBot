"""
Standard API response formats.
"""
from typing import Any, Dict, Optional, List
from pydantic import BaseModel


class SuccessResponse(BaseModel):
    """Standard success response"""
    success: bool = True
    data: Any
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response"""
    success: bool = False
    error: Dict[str, Any]


class PaginatedResponse(BaseModel):
    """Paginated list response"""
    success: bool = True
    data: List[Any]
    pagination: Dict[str, Any]
    
    @classmethod
    def create(
        cls,
        items: List[Any],
        page: int,
        per_page: int,
        total: int
    ):
        """Create paginated response"""
        total_pages = (total + per_page - 1) // per_page
        
        return cls(
            data=items,
            pagination={
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        )


def success_response(data: Any, message: Optional[str] = None) -> Dict[str, Any]:
    """Create success response dictionary"""
    response = {"success": True, "data": data}
    if message:
        response["message"] = message
    return response


def error_response(code: str, message: str, details: Optional[Dict] = None) -> Dict[str, Any]:
    """Create error response dictionary"""
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {}
        }
    }
