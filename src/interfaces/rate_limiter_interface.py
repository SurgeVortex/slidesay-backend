"""
Rate Limiter Interface.

Defines the contract for rate limiting services.
"""

from abc import ABC, abstractmethod

import azure.functions as func


class IRateLimiter(ABC):
    """Interface for rate limiting services."""

    @abstractmethod
    async def check_rate_limit(
        self, req: func.HttpRequest, user_id: str | None = None, endpoint: str | None = None
    ) -> tuple[bool, dict | None]:
        """
        Check if request is within rate limits.
        Args:
            req: Azure Function HTTP request
            user_id: Authenticated user ID (if available)
            endpoint: Endpoint path for specific limits
        Returns:
            Tuple of (is_allowed, rate_limit_info)
            rate_limit_info contains: limit, remaining, reset_time
        """
        pass

    @abstractmethod
    async def check_rate_limit_by_key(
        self, key: str, user_id: str | None = None, endpoint: str | None = None
    ) -> tuple[bool, dict | None]:
        """
        Check if request is within rate limits using a string key.
        Args:
            key: Rate limit key (IP address or identifier)
            user_id: Authenticated user ID (if available)
            endpoint: Endpoint path for specific limits
        Returns:
            Tuple of (is_allowed, rate_limit_info)
            rate_limit_info contains: limit, remaining, reset_time
        """
        pass

    @abstractmethod
    def create_rate_limit_response(self, rate_limit_info: dict) -> func.HttpResponse:
        """
        Create HTTP 429 response with rate limit headers.
        Args:
            rate_limit_info: Rate limit information
        Returns:
            HTTP 429 response
        """
        pass

    @abstractmethod
    def add_rate_limit_headers(
        self, response: func.HttpResponse, rate_limit_info: dict | None
    ) -> func.HttpResponse:
        """
        Add rate limit headers to successful response.
        Args:
            response: HTTP response to add headers to
            rate_limit_info: Rate limit information
        Returns:
            Response with rate limit headers
        """
        pass
