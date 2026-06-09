"""Standardized API error codes and response models."""
from pydantic import BaseModel


class APIErrorDetail(BaseModel):
    """Standard error detail format."""
    code: str
    detail: str
    message: str


class APIError(BaseModel):
    """Standard error response wrapper."""
    error: APIErrorDetail


# Common error codes
class ErrorCodes:
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    TENANT_NOT_FOUND = "TENANT_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    PAYMENT_REQUIRED = "PAYMENT_REQUIRED"
    CSRF_ERROR = "CSRF_ERROR"
