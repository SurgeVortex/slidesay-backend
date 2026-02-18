"""
Authentication Service Interface.

Defines the contract for authentication services.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import azure.functions as func

if TYPE_CHECKING:
    from src.auth.auth_service import User


@dataclass
class AuthResult:
    """Authentication result."""

    success: bool
    user_claims: dict[str, Any] | None = None
    error_message: str | None = None


class IAuthService(ABC):
    """Interface for authentication services."""

    @abstractmethod
    async def validate_token(self, token: str) -> dict[str, Any] | None:
        """
        Validate JWT token and return claims.
        Args:
            token: JWT access token
        Returns:
            Dictionary of claims if valid, None otherwise
        """
        pass

    @abstractmethod
    async def validate_request(self, req: func.HttpRequest) -> AuthResult:
        """
        Validate HTTP request authentication.
        Args:
            req: Azure Function HTTP request
        Returns:
            AuthResult with success status and claims
        """
        pass

    @abstractmethod
    async def get_or_create_user(
        self,
        token_payload: dict[str, Any],
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple["User", bool] | None:
        """
        Get or create user from token claims.
        Args:
            token_payload: JWT token claims
            ip_address: Request IP address for audit logging
            user_agent: Request user agent for audit logging
        Returns:
            Tuple of (User object, is_new_user flag) if successful, None otherwise
        """
        pass
