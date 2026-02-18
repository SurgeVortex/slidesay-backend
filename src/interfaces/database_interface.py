"""
Database Service Interface.

Defines the contract for database services.
"""

from abc import ABC, abstractmethod
from typing import Any


class IDatabaseService(ABC):
    """Interface for database services."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize database connection."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check database health."""
        pass

    # User operations

    @abstractmethod
    async def create_user(self, user_data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new user."""
        pass

    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """Get user by ID."""
        pass

    @abstractmethod
    async def update_user(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """Update user record."""
        pass

    @abstractmethod
    async def delete_user(self, user_id: str) -> bool:
        """Delete user (soft delete)."""
        pass

    # Audit logging

    @abstractmethod
    async def create_audit_log(self, audit_data: dict[str, Any]) -> dict[str, Any] | None:
        """Create audit log entry."""
        pass

    @abstractmethod
    async def get_audit_logs(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get audit logs for a user."""
        pass

    # Generic query

    @abstractmethod
    async def query_items(
        self,
        container_name: str,
        query: str,
        parameters: list[dict[str, Any]] | None = None,
        partition_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a custom query."""
        pass

    @abstractmethod
    def get_container_client(self, container_name: str) -> Any:
        """
        Get container client for direct operations.
        Note: This is an escape hatch for advanced scenarios.
        Prefer using the higher-level methods when possible.
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close database connections."""
        pass
