"""Interface definitions for dependency injection.

This module defines abstract base classes (protocols) for all services.
This allows easy swapping of implementations without changing business logic.
"""

from .auth_interface import AuthResult, IAuthService
from .database_interface import IDatabaseService
from .endpoint_interface import HttpRequest, HttpResponse, IEndpointService
from .monitoring_interface import IMonitoringService
from .rate_limiter_interface import IRateLimiter

__all__ = [
    "IAuthService",
    "AuthResult",
    "IDatabaseService",
    "IMonitoringService",
    "IRateLimiter",
    "IEndpointService",
    "HttpRequest",
    "HttpResponse",
]
