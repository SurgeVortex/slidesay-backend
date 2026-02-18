"""Test database service with real implementations and in-memory test doubles."""

from datetime import datetime
from unittest.mock import patch

import pytest

from tests.test_doubles import InMemoryDatabaseService


class TestDatabaseServiceBusinessLogic:
    """Test database service business logic with in-memory implementation."""

    @pytest.fixture
    async def db_service(self):
        """Create and initialize in-memory database service."""
        service = InMemoryDatabaseService()
        await service.initialize()
        return service

    @pytest.mark.asyncio
    async def test_health_check_when_initialized(self, db_service):
        """Test health check returns True when initialized."""
        is_healthy = await db_service.health_check()
        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_before_initialization(self):
        """Test health check returns False before initialization."""
        service = InMemoryDatabaseService()
        is_healthy = await service.health_check()
        assert is_healthy is False

    @pytest.mark.asyncio
    async def test_health_check_after_close(self, db_service):
        """Test health check returns False after close."""
        await db_service.close()
        is_healthy = await db_service.health_check()
        assert is_healthy is False

    @pytest.mark.asyncio
    async def test_create_user_auto_generates_timestamp(self, db_service):
        """Test that create_user automatically adds createdAt timestamp."""
        user_data = {"id": "user123", "email": "test@example.com", "name": "Test User"}

        result = await db_service.create_user(user_data)

        # Verify timestamp was added
        assert result is not None
        assert "createdAt" in result
        assert result["id"] == "user123"

        # Verify it's a valid ISO timestamp
        datetime.fromisoformat(result["createdAt"])

    @pytest.mark.asyncio
    async def test_create_user_sets_partition_key(self, db_service):
        """Test that create_user sets userId to match id (partition key)."""
        user_data = {"id": "user123", "email": "test@example.com"}

        result = await db_service.create_user(user_data)

        # Verify userId matches id (partition key requirement)
        assert result is not None
        assert result["userId"] == result["id"]
        assert result["userId"] == "user123"

    @pytest.mark.asyncio
    async def test_create_user_preserves_existing_timestamp(self, db_service):
        """Test that create_user preserves existing createdAt if provided."""
        custom_timestamp = "2023-01-01T00:00:00Z"
        user_data = {"id": "user123", "email": "test@example.com", "createdAt": custom_timestamp}

        result = await db_service.create_user(user_data)

        # Verify existing timestamp was not overwritten
        assert result is not None
        assert result["createdAt"] == custom_timestamp

    @pytest.mark.asyncio
    async def test_get_user_by_id_returns_created_user(self, db_service):
        """Test retrieving a user that exists."""
        user_data = {"id": "user123", "email": "test@example.com", "name": "Test User"}

        await db_service.create_user(user_data)
        result = await db_service.get_user_by_id("user123")

        assert result is not None
        assert result["id"] == "user123"
        assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_user_by_id_returns_none_when_not_found(self, db_service):
        """Test retrieving a user that doesn't exist returns None."""
        result = await db_service.get_user_by_id("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_user_merges_data_correctly(self, db_service):
        """Test that update_user merges new data with existing user data."""
        # Create initial user
        initial_data = {
            "id": "user123",
            "email": "old@example.com",
            "name": "Old Name",
            "createdAt": "2023-01-01T00:00:00Z",
        }
        await db_service.create_user(initial_data)

        # Update user
        updates = {"name": "New Name", "email": "new@example.com"}
        result = await db_service.update_user("user123", updates)

        # Verify merge happened correctly
        assert result is not None
        assert result["name"] == "New Name"  # Updated
        assert result["email"] == "new@example.com"  # Updated
        assert result["createdAt"] == "2023-01-01T00:00:00Z"  # Preserved
        assert result["id"] == "user123"  # Preserved

    @pytest.mark.asyncio
    async def test_update_user_returns_none_when_not_found(self, db_service):
        """Test updating a non-existent user returns None."""
        result = await db_service.update_user("nonexistent", {"name": "Test"})
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_user_soft_deletes(self, db_service):
        """Test that delete_user performs soft delete (sets isActive=False)."""
        # Create user
        user_data = {"id": "user123", "email": "test@example.com", "isActive": True}
        await db_service.create_user(user_data)

        # Delete user
        success = await db_service.delete_user("user123")
        assert success is True

        # Verify user still exists but is inactive
        user = await db_service.get_user_by_id("user123")
        assert user is not None
        assert user["isActive"] is False

    @pytest.mark.asyncio
    async def test_create_audit_log_generates_id(self, db_service):
        """Test that create_audit_log generates UUID if id is missing."""
        audit_data = {"userId": "user123", "action": "user_login"}

        result = await db_service.create_audit_log(audit_data)

        # Verify ID was generated
        assert result is not None
        assert "id" in result
        assert len(result["id"]) == 36  # UUID length

    @pytest.mark.asyncio
    async def test_create_audit_log_adds_timestamp(self, db_service):
        """Test that create_audit_log adds timestamp if missing."""
        audit_data = {"id": "audit123", "userId": "user123", "action": "user_login"}

        result = await db_service.create_audit_log(audit_data)

        # Verify timestamp was added
        assert result is not None
        assert "timestamp" in result
        # Verify it's a valid ISO timestamp
        datetime.fromisoformat(result["timestamp"])

    @pytest.mark.asyncio
    async def test_create_audit_log_initializes_metadata(self, db_service):
        """Test that create_audit_log initializes metadata as empty dict."""
        audit_data = {"id": "audit123", "userId": "user123", "action": "user_login"}

        result = await db_service.create_audit_log(audit_data)

        # Verify metadata was initialized
        assert result is not None
        assert "metadata" in result
        assert isinstance(result["metadata"], dict)
        assert len(result["metadata"]) == 0

    @pytest.mark.asyncio
    async def test_create_audit_log_preserves_metadata(self, db_service):
        """Test that create_audit_log preserves existing metadata."""
        audit_data = {
            "id": "audit123",
            "userId": "user123",
            "action": "user_login",
            "metadata": {"key": "value"},
        }

        result = await db_service.create_audit_log(audit_data)

        # Verify metadata was preserved
        assert result is not None
        assert result["metadata"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_create_audit_log_requires_user_id(self, db_service):
        """Test that create_audit_log validates userId is required."""
        audit_data = {"id": "audit123", "action": "user_login"}

        with pytest.raises(ValueError, match="userId is required"):
            await db_service.create_audit_log(audit_data)

    @pytest.mark.asyncio
    async def test_create_audit_log_requires_action(self, db_service):
        """Test that create_audit_log validates action is required."""
        audit_data = {"id": "audit123", "userId": "user123"}

        with pytest.raises(ValueError, match="action is required"):
            await db_service.create_audit_log(audit_data)

    @pytest.mark.asyncio
    async def test_get_audit_logs_filters_by_user_id(self, db_service):
        """Test that get_audit_logs returns only logs for specified user."""
        # Create logs for different users
        await db_service.create_audit_log({"userId": "user1", "action": "login"})
        await db_service.create_audit_log({"userId": "user2", "action": "logout"})
        await db_service.create_audit_log({"userId": "user1", "action": "update_profile"})

        # Get logs for user1
        logs = await db_service.get_audit_logs("user1")

        # Verify only user1 logs are returned
        assert len(logs) == 2
        assert all(log["userId"] == "user1" for log in logs)

    @pytest.mark.asyncio
    async def test_get_audit_logs_sorts_by_timestamp_descending(self, db_service):
        """Test that get_audit_logs returns logs sorted by timestamp (newest first)."""
        # Create logs with different timestamps
        await db_service.create_audit_log(
            {"userId": "user1", "action": "first", "timestamp": "2023-01-01T00:00:00Z"}
        )
        await db_service.create_audit_log(
            {"userId": "user1", "action": "third", "timestamp": "2023-01-03T00:00:00Z"}
        )
        await db_service.create_audit_log(
            {"userId": "user1", "action": "second", "timestamp": "2023-01-02T00:00:00Z"}
        )

        logs = await db_service.get_audit_logs("user1")

        # Verify order (newest first)
        assert len(logs) == 3
        assert logs[0]["action"] == "third"
        assert logs[1]["action"] == "second"
        assert logs[2]["action"] == "first"

    @pytest.mark.asyncio
    async def test_get_audit_logs_respects_limit(self, db_service):
        """Test that get_audit_logs respects the limit parameter."""
        # Create 5 logs
        for i in range(5):
            await db_service.create_audit_log({"userId": "user1", "action": f"action_{i}"})

        # Get only 3 logs
        logs = await db_service.get_audit_logs("user1", limit=3)

        # Verify limit was applied
        assert len(logs) == 3


class TestCosmosServiceArchitecture:
    """Test Cosmos DB specific architecture with mocked SDK."""

    @pytest.mark.asyncio
    @patch.dict(
        "os.environ",
        {
            "COSMOSDB_ENDPOINT": "https://test.documents.azure.com:443/",
            "COSMOSDB_DATABASE_NAME": "test_db",
        },
    )
    @patch("src.database.cosmos_service.CosmosClient")
    @patch("src.database.cosmos_service.ChainedTokenCredential")
    async def test_uses_chained_token_credential(self, mock_chained_cred, mock_cosmos_client):
        """Test that CosmosService uses ChainedTokenCredential (ManagedIdentity -> AzureCLI)."""
        from azure.identity import AzureCliCredential, ManagedIdentityCredential

        from src.database.cosmos_service import CosmosService

        service = CosmosService()
        await service.initialize()

        # Verify ChainedTokenCredential was created with correct credential chain
        mock_chained_cred.assert_called_once()
        call_args = mock_chained_cred.call_args[0]
        assert len(call_args) == 2
        assert isinstance(call_args[0], ManagedIdentityCredential)
        assert isinstance(call_args[1], AzureCliCredential)

        # Verify CosmosClient was initialized with endpoint and credential
        mock_cosmos_client.assert_called_once()
        cosmos_call_args = mock_cosmos_client.call_args[0]
        assert len(cosmos_call_args) == 2
        assert cosmos_call_args[0] == "https://test.documents.azure.com:443/"
        assert cosmos_call_args[1] == mock_chained_cred.return_value

    @pytest.mark.asyncio
    @patch.dict(
        "os.environ",
        {
            "COSMOSDB_ENDPOINT": "https://test.documents.azure.com:443/",
            "COSMOSDB_DATABASE_NAME": "test_db",
        },
    )
    @patch("src.database.cosmos_service.CosmosClient")
    async def test_initializes_three_containers(self, mock_cosmos_client):
        """Test that service initializes users, auditlogs, and ratelimits containers."""
        from unittest.mock import Mock

        from src.database.cosmos_service import CosmosService

        mock_database = Mock()
        mock_cosmos_client.return_value.get_database_client.return_value = mock_database

        service = CosmosService()
        await service.initialize()

        # Verify all three containers were accessed
        assert mock_database.get_container_client.call_count == 3
        container_names = [call[0][0] for call in mock_database.get_container_client.call_args_list]
        assert "users" in container_names
        assert "auditlogs" in container_names
        assert "ratelimits" in container_names
