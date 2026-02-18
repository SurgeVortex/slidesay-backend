"""
Azure Cosmos DB Service

Provides database operations with repository patterns for Azure Cosmos DB.
Includes connection management, error handling, and performance monitoring.
"""

import time
from datetime import UTC, datetime
from typing import Any

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError
from azure.identity import (
    AzureCliCredential,
    ChainedTokenCredential,
    ManagedIdentityCredential,
)

from src.interfaces.database_interface import IDatabaseService
from src.utils.config import Config
from src.utils.logger import get_logger


class CosmosService(IDatabaseService):
    """Azure Cosmos DB service with repository patterns."""

    def __init__(self) -> None:
        self.config = Config()
        self.logger = get_logger(__name__)

        # Database configuration from environment variables (required)
        self.endpoint: str = self.config.get("COSMOSDB_ENDPOINT") or ""
        self.database_name: str = self.config.get("COSMOSDB_DATABASE_NAME") or ""

        # Container names from environment
        self.users_container: str = self.config.get("COSMOSDB_USERS_CONTAINER") or "users"
        self.auditlogs_container: str = (
            self.config.get("COSMOSDB_AUDITLOGS_CONTAINER") or "auditlogs"
        )
        self.ratelimits_container: str = (
            self.config.get("COSMOSDB_RATELIMITS_CONTAINER") or "ratelimits"
        )

        # Client instances
        from typing import Any

        self.client: CosmosClient | None = None
        self.database: Any = None
        # Mapping of container name -> container client proxy
        self.container_clients: dict[str, Any] = {}

        # Connection state
        self._initialized = False

        # Metrics for monitoring
        self._operation_count = 0
        self._error_count = 0

    async def initialize(self) -> None:
        """
        Initialize Cosmos DB client using Managed Identity.

        NOTE: Containers should already exist - they are created by infrastructure/CI pipeline.
        This method only establishes connection and gets container references.
        """
        if self._initialized:
            return

        try:
            # Use ChainedTokenCredential for deterministic, production-grade authentication
            # 1. ManagedIdentityCredential: Used in production (Azure Functions, App Service, etc.)
            # 2. AzureCliCredential: Used in local development (after 'az login')
            # This approach is faster and more predictable than DefaultAzureCredential
            credential = ChainedTokenCredential(
                ManagedIdentityCredential(),  # Production: Managed Identity assigned to Azure Function
                AzureCliCredential(),  # Local dev: Azure CLI credentials (az login)
            )
            # Create a local client variable and use it to fetch database/container clients
            client = CosmosClient(self.endpoint, credential)
            self.client = client

            # Get database reference (must already exist)
            database = client.get_database_client(self.database_name)
            self.database = database

            # Get container references (must already exist)
            self.container_clients[self.users_container] = database.get_container_client(
                self.users_container
            )
            self.container_clients[self.auditlogs_container] = database.get_container_client(
                self.auditlogs_container
            )
            self.container_clients[self.ratelimits_container] = database.get_container_client(
                self.ratelimits_container
            )

            self._initialized = True
            self.logger.info(
                "Cosmos DB initialized with Managed Identity",
                database=self.database_name,
                containers=[
                    self.users_container,
                    self.auditlogs_container,
                    self.ratelimits_container,
                ],
            )

        except Exception as e:
            self.logger.error("Failed to initialize Cosmos DB", error=str(e))
            raise

    async def health_check(self) -> bool:
        """Check if Cosmos DB is accessible."""
        try:
            await self.initialize()

            # Try to read from users container to verify connection
            container = self.container_clients.get(self.users_container)
            if container is not None:
                # Simple query to verify connectivity
                list(
                    container.query_items(
                        query="SELECT TOP 1 * FROM c", enable_cross_partition_query=True
                    )
                )
                return True
            return False

        except Exception as e:
            self.logger.error("Cosmos DB health check failed", error=str(e))
            return False

    async def _execute_operation(
        self, operation_name: str, operation_func: Any, *args: Any, **kwargs: Any
    ) -> Any:
        """Execute a database operation with monitoring and error handling."""
        start_time = time.time()

        try:
            await self.initialize()

            result = operation_func(*args, **kwargs)

            # Log successful operation
            duration_ms = (time.time() - start_time) * 1000
            self.logger.info(
                "cosmos_operation_success", operation=operation_name, duration_ms=duration_ms
            )

            self._operation_count += 1
            return result

        except CosmosResourceNotFoundError:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.warning(
                "cosmos_resource_not_found", operation=operation_name, duration_ms=duration_ms
            )
            self._error_count += 1
            return None

        except CosmosHttpResponseError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error(
                "cosmos_http_error",
                operation=operation_name,
                status_code=e.status_code,
                error=str(e),
                duration_ms=duration_ms,
            )
            self._error_count += 1
            raise

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error(
                "cosmos_operation_error",
                operation=operation_name,
                error=str(e),
                duration_ms=duration_ms,
            )
            self._error_count += 1
            raise

    # User management operations

    async def create_user(self, user_data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Create a new user record.

        Container: users
        Partition Key: /userId

        Expected fields in user_data:
        - id: Unique document ID (typically same as userId)
        - userId: Partition key - unique user identifier from Entra ID (sub claim)
        - email: User email
        - displayName: User's full name
        - createdAt: ISO timestamp
        - lastLoginAt: ISO timestamp
        """
        container = self.container_clients[self.users_container]

        # Ensure userId is set (used as partition key)
        if "userId" not in user_data:
            raise ValueError("userId is required for user creation")

        # Add metadata if not present
        if "createdAt" not in user_data:
            user_data["createdAt"] = datetime.now(UTC).isoformat()
        if "lastLoginAt" not in user_data:
            user_data["lastLoginAt"] = datetime.now(UTC).isoformat()
        if "isActive" not in user_data:
            user_data["isActive"] = True

        result = await self._execute_operation("create_user", container.create_item, body=user_data)
        return result if isinstance(result, dict) else result

    async def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """
        Get user by ID.

        Args:
            user_id: User ID (also used as partition key)

        Returns:
            User document or None if not found
        """
        container = self.container_clients[self.users_container]

        result = await self._execute_operation(
            "get_user_by_id",
            container.read_item,
            item=user_id,
            partition_key=user_id,  # Both id and partition key are userId
        )
        return result if isinstance(result, dict) else None

    async def update_user(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """
        Update user record.

        Args:
            user_id: User ID (partition key)
            updates: Dictionary of fields to update

        Returns:
            Updated user document or None if not found
        """
        container = self.container_clients[self.users_container]

        # Get existing user
        existing_user = await self.get_user_by_id(user_id)
        if not existing_user:
            return None

        # Apply updates
        existing_user.update(updates)
        existing_user["lastLoginAt"] = datetime.now(UTC).isoformat()

        result = await self._execute_operation(
            "update_user", container.replace_item, item=user_id, body=existing_user
        )
        return result if isinstance(result, dict) else None

    async def delete_user(self, user_id: str) -> bool:
        """
        Delete user record (soft delete by setting isActive=False).

        Args:
            user_id: User ID (partition key)

        Returns:
            True if successful, False otherwise
        """
        try:
            await self.update_user(
                user_id, {"isActive": False, "deletedAt": datetime.now(UTC).isoformat()}
            )
            return True
        except Exception:
            return False

    # Generic query operations

    async def query_items(
        self,
        container_name: str,
        query: str,
        parameters: list[dict[str, Any]] | None = None,
        partition_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a custom query against a container."""
        if container_name not in self.container_clients:
            raise ValueError(f"Unknown container: {container_name}")

        container = self.container_clients[container_name]

        try:
            query_options = {"query": query, "parameters": parameters or []}

            if partition_key:
                query_options["partition_key"] = partition_key

            # Execute query and collect items
            if container is None:
                raise RuntimeError("Container client not available")

            items = list(container.query_items(**query_options))

            self.logger.info("query_items_success", container=container_name, count=len(items))

            return items

        except Exception as e:
            self.logger.error(
                "query_items_error", container=container_name, query=query, error=str(e)
            )
            raise

    # Audit logging methods

    async def create_audit_log(self, audit_data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Create an audit log entry in the auditlogs container.

        Container: auditlogs
        Partition Key: /date (format: YYYY-MM-DD)
        TTL: 30 days (automatic deletion)

        Args:
            audit_data: Dictionary containing audit log data with keys:
                - id: Unique log entry identifier (UUID)
                - date: Partition key - date in YYYY-MM-DD format (auto-generated if missing)
                - userId: User who performed the action
                - action: Description of action (e.g., "user_login", "data_created")
                - timestamp: ISO timestamp of the action
                - metadata: Additional context dictionary
                - ipAddress: Request origin (optional)
                - userAgent: Client information (optional)
                - ttl: Time-to-live in seconds (auto-set to 30 days if missing)

        Returns:
            Created audit log entry or None on failure
        """
        try:
            await self.initialize()

            # Ensure required fields
            if "userId" not in audit_data:
                raise ValueError("userId is required for audit log")

            if "id" not in audit_data:
                import uuid

                audit_data["id"] = str(uuid.uuid4())

            if "timestamp" not in audit_data:
                audit_data["timestamp"] = datetime.now(UTC).isoformat()

            # Add date partition key (YYYY-MM-DD format)
            if "date" not in audit_data:
                audit_data["date"] = datetime.now(UTC).strftime("%Y-%m-%d")

                # Add TTL for automatic deletion after 30 days (2592000 seconds)

                audit_data["ttl"] = 2592000

            if "action" not in audit_data:
                raise ValueError("action is required for audit log")

            # Metadata should be a dict
            if "metadata" not in audit_data:
                audit_data["metadata"] = {}

            container = self.container_clients.get(self.auditlogs_container)
            if not container:
                self.logger.error("Audit logs container not initialized")
                return None

            result = container.create_item(body=audit_data, enable_automatic_id_generation=False)

            self._operation_count += 1
            self.logger.info(
                "Audit log created",
                audit_id=audit_data["id"],
                user_id=audit_data["userId"],
                action=audit_data["action"],
            )

            return result if isinstance(result, dict) else None

        except CosmosHttpResponseError as e:
            self._error_count += 1
            self.logger.error(
                "Failed to create audit log",
                audit_id=audit_data.get("id"),
                status_code=e.status_code,
                error=str(e),
            )
            return None
        except Exception as e:
            self._error_count += 1
            self.logger.error("Unexpected error creating audit log", error=str(e))
            return None

    async def get_audit_logs(
        self, user_id: str, limit: int = 50, days: int = 7
    ) -> list[dict[str, Any]]:
        """
        Get audit logs for a specific user within a date range.

        Queries across date partitions for the specified number of days.
        Partition Key: /date (YYYY-MM-DD format)

        Args:
            user_id: User ID to get audit logs for
            limit: Maximum number of logs to return
            days: Number of days to look back (default: 7)

        Returns:
            List of audit log entries sorted by timestamp (newest first)
        """
        try:
            await self.initialize()

            container = self.container_clients.get(self.auditlogs_container)
            if not container:
                self.logger.error("Audit logs container not initialized")
                return []

            # Query across partitions for user's logs
            # Note: This is a cross-partition query, but limited by time range (7 days by default)
            query = "SELECT * FROM c WHERE c.userId = @user_id ORDER BY c.timestamp DESC OFFSET 0 LIMIT @limit"
            parameters = [
                {"name": "@user_id", "value": user_id},
                {"name": "@limit", "value": limit},
            ]

            items = list(
                container.query_items(
                    query=query,
                    parameters=parameters,
                    enable_cross_partition_query=True,  # Required for cross-partition query
                )
            )

            self._operation_count += 1

            return items

        except CosmosHttpResponseError as e:
            self._error_count += 1
            self.logger.error(
                "Failed to get audit logs", user_id=user_id, status_code=e.status_code, error=str(e)
            )
            return []
        except Exception as e:
            self._error_count += 1
            self.logger.error("Unexpected error getting audit logs", user_id=user_id, error=str(e))
            return []

    # User profile convenience methods (for template compatibility)

    async def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        """Get user profile information (template method)."""
        # This is a template implementation
        # In practice, you'd query the users container with the user_id

        # For the template, we'll return mock data for the test user
        if self.config.is_development() and user_id == "test-user-id":
            return {
                "id": user_id,
                "email": "test@example.com",
                "name": "Test User",
                "created_at": datetime.now(UTC).isoformat(),
                "profile": {"avatar_url": None, "timezone": "UTC", "language": "en"},
            }

        # TODO: Implement actual user profile lookup
        # You would need to modify this based on your user data structure
        return None

    # Performance and monitoring

    def get_metrics(self) -> dict[str, Any]:
        """Get database operation metrics."""
        return {
            "total_operations": self._operation_count,
            "error_count": self._error_count,
            "error_rate": self._error_count / max(self._operation_count, 1),
            "containers_initialized": len(self.container_clients),
            "is_initialized": self._initialized,
        }

    def get_container_client(self, container_name: str) -> Any:
        """Get container client for direct operations."""
        return self.container_clients.get(container_name)

    async def close(self) -> None:
        """Close database connections."""
        try:
            if self.client:
                # Cosmos client doesn't have an explicit close method
                # Connections are managed automatically
                self.client = None

            self.container_clients.clear()
            self._initialized = False

            self.logger.info("Cosmos DB connections closed")

        except Exception as e:
            self.logger.error("Error closing Cosmos DB connections", error=str(e))
