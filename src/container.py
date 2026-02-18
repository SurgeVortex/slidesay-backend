"""
Dependency Injection Container.

Centralizes service instantiation and dependency management.
This makes it easy to swap implementations without changing business logic.
"""

from src.interfaces import (
    IAuthService,
    IDatabaseService,
    IEndpointService,
    IMonitoringService,
    IRateLimiter,
)


class ServiceContainer:
    """
    Dependency injection container.
    Manages service instances and their dependencies.
    Supports lazy initialization and singleton pattern.
    """

    def __init__(self) -> None:
        self._database_service: IDatabaseService | None = None
        self._auth_service: IAuthService | None = None
        self._rate_limiter: IRateLimiter | None = None
        self._endpoint_service: IEndpointService | None = None
        # Monitoring service is created per-request, not singleton

    def get_database_service(self) -> IDatabaseService:
        """Get database service (singleton)."""
        if self._database_service is None:
            from src.database.cosmos_service import CosmosService

            self._database_service = CosmosService()
        return self._database_service

    def get_auth_service(self) -> IAuthService:
        """Get authentication service (singleton)."""
        if self._auth_service is None:
            from src.auth.auth_service import AuthService

            self._auth_service = AuthService(database_service=self.get_database_service())
        return self._auth_service

    def get_rate_limiter(self) -> IRateLimiter:
        """Get rate limiter (singleton)."""
        if self._rate_limiter is None:
            from src.middleware.rate_limiter import RateLimiter

            self._rate_limiter = RateLimiter(database_service=self.get_database_service())
        return self._rate_limiter

    def create_monitoring_service(self) -> IMonitoringService:
        """Create new monitoring service (per-request)."""
        from src.monitoring.monitor import MonitoringService

        return MonitoringService(database_service=self.get_database_service())

    def get_endpoint_service(self) -> IEndpointService:
        """Get endpoint service (singleton)."""
        if self._endpoint_service is None:
            from src.services.endpoint_service import EndpointService
            from src.utils.config import Config

            self._endpoint_service = EndpointService(
                auth_service=self.get_auth_service(),
                database_service=self.get_database_service(),
                rate_limiter=self.get_rate_limiter(),
                config=Config(),
            )
        return self._endpoint_service

    def reset(self) -> None:
        """Reset all services (useful for testing)."""
        self._database_service = None
        self._auth_service = None
        self._rate_limiter = None
        self._endpoint_service = None


# Global container instance
_container: ServiceContainer | None = None


def get_container() -> ServiceContainer:
    """Get the global service container."""
    global _container
    if _container is None:
        _container = ServiceContainer()
    return _container


def reset_container() -> None:
    """Reset the global container (useful for testing)."""
    global _container
    if _container is not None:
        _container.reset()
    _container = None
