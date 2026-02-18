"""
Endpoint business logic interface.

Separates business logic from framework (Azure Functions, FastAPI, etc).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.interfaces.monitoring_interface import IMonitoringService


@dataclass
class HttpRequest:
    """Framework-agnostic HTTP request."""

    method: str
    path: str
    headers: dict[str, str]
    body: str | None = None
    query_params: dict[str, str] | None = None


@dataclass
class HttpResponse:
    """Framework-agnostic HTTP response."""

    body: str
    status_code: int
    headers: dict[str, str] | None = None


class IEndpointService(ABC):
    """Interface for endpoint business logic."""

    @abstractmethod
    async def health_check(self, monitor: "IMonitoringService") -> HttpResponse:
        """Health check endpoint logic."""
        pass

    @abstractmethod
    async def login(self, request: HttpRequest, monitor: "IMonitoringService") -> HttpResponse:
        """Login endpoint logic."""
        pass

    @abstractmethod
    async def get_profile(
        self, request: HttpRequest, monitor: "IMonitoringService"
    ) -> HttpResponse:
        """Get user profile endpoint logic."""
        pass
