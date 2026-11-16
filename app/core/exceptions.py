from typing import Optional, Dict, Any
from flask import jsonify


class AppException(Exception):
    status_code: int = 500
    error_code: str = "INTERNAL_SERVER_ERROR"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: Optional[str] = None,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message or self.message)
        if message:
            self.message = message
        if status_code:
            self.status_code = status_code
        if error_code:
            self.error_code = error_code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        rv = {
            "error": self.message,
            "error_code": self.error_code,
            "status": "error",
        }
        if self.details:
            rv["details"] = self.details
        return rv


class NotFoundException(AppException):
    status_code = 404
    error_code = "NOT_FOUND"
    message = "Resource not found."


class ValidationException(AppException):
    status_code = 400
    error_code = "VALIDATION_ERROR"
    message = "Invalid input provided."


class ConflictException(AppException):
    status_code = 409
    error_code = "CONFLICT"
    message = "Resource conflict detected."


class RateLimitException(AppException):
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"
    message = "Too many requests. Please slow down."


class BackendUnavailableException(AppException):
    status_code = 503
    error_code = "BACKEND_UNAVAILABLE"
    message = "The requested inference backend is currently unavailable."


class QuotaExhaustedException(AppException):
    status_code = 429
    error_code = "QUOTA_EXHAUSTED"
    message = "Inference quota exhausted on the free tier endpoint."
