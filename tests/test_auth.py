"""Test the authentication service with Microsoft Entra ID and real dependencies."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import jwt
import pytest

from src.auth.auth_service import AuthService
from tests.test_doubles import InMemoryDatabaseService


class TestAuthServiceBusinessLogic:
    """Test AuthService business logic with real database and mocked JWT validation."""

    @pytest.fixture
    async def db_service(self):
        """Create and initialize in-memory database service."""
        service = InMemoryDatabaseService()
        await service.initialize()
        return service

    @pytest.fixture
    def auth_service(self, db_service):
        """Create an auth service instance with real database."""
        with patch("src.auth.auth_service.Config") as mock_config:
            mock_config.return_value.get.side_effect = lambda key, default=None: {
                "AZURE_CLIENT_ID": "test-client-id",
                "AZURE_TENANT_ID": "test-tenant-id",
                "JWKS_URI": "https://test.microsoft.com/keys",
                "DEFAULT_USER_ROLES": "user",
                "ADMIN_EMAILS": "admin@example.com",
                "ENVIRONMENT": "testing",
            }.get(key, default)

            service = AuthService(database_service=db_service)
            return service

    @pytest.mark.asyncio
    async def test_get_or_create_user_creates_new_user_in_database(self, auth_service, db_service):
        """Test that new user is actually created in database."""
        token_payload = {"sub": "new-user-123", "email": "newuser@example.com", "name": "New User"}

        # Verify user doesn't exist yet
        existing = await db_service.get_user_by_id("new-user-123")
        assert existing is None

        # Create user via auth service
        result = await auth_service.get_or_create_user(
            token_payload, ip_address="192.168.1.1", user_agent="Mozilla/5.0"
        )

        assert result is not None
        user, is_new_user = result
        assert is_new_user is True

        # Verify user now exists in database
        db_user = await db_service.get_user_by_id("new-user-123")
        assert db_user is not None
        assert db_user["email"] == "newuser@example.com"
        assert db_user["name"] == "New User"
        assert db_user["isActive"] is True

    @pytest.mark.asyncio
    async def test_get_or_create_user_existing_user_updates_last_login(
        self, auth_service, db_service
    ):
        """Test that existing user's lastLoginAt is updated."""
        # Create user first
        await db_service.create_user(
            {
                "id": "existing-user",
                "email": "existing@example.com",
                "name": "Existing User",
                "lastLoginAt": "2023-01-01T00:00:00Z",
            }
        )

        token_payload = {
            "sub": "existing-user",
            "email": "existing@example.com",
            "name": "Existing User",
        }

        # Login with existing user
        result = await auth_service.get_or_create_user(token_payload)

        assert result is not None
        user, is_new_user = result
        assert is_new_user is False

        # Verify lastLoginAt was updated in database
        db_user = await db_service.get_user_by_id("existing-user")
        assert db_user["lastLoginAt"] != "2023-01-01T00:00:00Z"
        # Verify it's a recent timestamp
        last_login = datetime.fromisoformat(db_user["lastLoginAt"])
        now = datetime.now(UTC)
        assert (now - last_login).total_seconds() < 5  # Within 5 seconds

    @pytest.mark.asyncio
    async def test_get_or_create_user_admin_role_persisted(self, auth_service, db_service):
        """Test that admin role is persisted in database."""
        token_payload = {
            "sub": "admin-user",
            "email": "admin@example.com",  # Matches ADMIN_EMAILS in fixture
            "name": "Admin User",
        }

        result = await auth_service.get_or_create_user(token_payload)

        assert result is not None
        user, _ = result
        assert "admin" in user.roles

        # Verify admin role is in database
        db_user = await db_service.get_user_by_id("admin-user")
        assert "admin" in db_user["roles"]
        assert "user" in db_user["roles"]  # Default role also present

    @pytest.mark.asyncio
    async def test_get_or_create_user_display_name_logic(self, auth_service, db_service):
        """Test display name selection logic with real database."""
        # Test 1: Full name takes priority
        result1 = await auth_service.get_or_create_user(
            {
                "sub": "user1",
                "email": "user1@example.com",
                "name": "Full Name",
                "given_name": "First",
                "family_name": "Last",
            }
        )
        user1, _ = result1
        assert user1.display_name == "Full Name"

        # Test 2: Given + family name when no full name
        result2 = await auth_service.get_or_create_user(
            {
                "sub": "user2",
                "email": "user2@example.com",
                "given_name": "First",
                "family_name": "Last",
            }
        )
        user2, _ = result2
        assert user2.display_name == "First Last"

        # Test 3: Email username as fallback
        result3 = await auth_service.get_or_create_user(
            {"sub": "user3", "email": "username@example.com"}
        )
        user3, _ = result3
        assert user3.display_name == "username"

    @pytest.mark.asyncio
    async def test_get_or_create_user_validates_required_fields(self, auth_service):
        """Test that missing required fields are handled correctly."""
        # Missing sub
        result1 = await auth_service.get_or_create_user({"email": "test@example.com"})
        assert result1 is None

        # Missing email
        result2 = await auth_service.get_or_create_user({"sub": "user-123"})
        assert result2 is None

    @pytest.mark.asyncio
    async def test_multiple_users_can_be_created(self, auth_service, db_service):
        """Test that multiple users can be created and retrieved."""
        # Create first user
        await auth_service.get_or_create_user(
            {"sub": "user1", "email": "user1@example.com", "name": "User One"}
        )

        # Create second user
        await auth_service.get_or_create_user(
            {"sub": "user2", "email": "user2@example.com", "name": "User Two"}
        )

        # Verify both exist
        user1 = await db_service.get_user_by_id("user1")
        user2 = await db_service.get_user_by_id("user2")

        assert user1 is not None
        assert user2 is not None
        assert user1["email"] == "user1@example.com"
        assert user2["email"] == "user2@example.com"


class TestAuthServiceJWTValidation:
    """Test JWT validation with mocked PyJWKClient (external dependency)."""

    @pytest.fixture
    def auth_service_with_mock_db(self):
        """Create auth service with mock database for JWT-only tests."""
        mock_db = InMemoryDatabaseService()

        with patch("src.auth.auth_service.Config") as mock_config:
            mock_config.return_value.get.side_effect = lambda key, default=None: {
                "AZURE_CLIENT_ID": "test-client-id",
                "AZURE_TENANT_ID": "test-tenant-id",
                "JWKS_URI": "https://test.microsoft.com/keys",
                "DEFAULT_USER_ROLES": "user",
                "ADMIN_EMAILS": "",
                "ENVIRONMENT": "testing",
            }.get(key, default)

            service = AuthService(database_service=mock_db)
            return service

    @pytest.mark.asyncio
    async def test_validate_token_success(self, auth_service_with_mock_db):
        """Test successful Microsoft Entra ID token validation."""
        auth_service = auth_service_with_mock_db
        mock_signing_key = Mock()
        mock_signing_key.key = "test-key"

        valid_payload = {
            "sub": "user-123",
            "email": "test@example.com",
            "name": "Test User",
            "aud": "test-client-id",
            "iss": "https://login.microsoftonline.com/test-tenant-id/v2.0",
            "exp": datetime.now(UTC).timestamp() + 3600,
            "iat": datetime.now(UTC).timestamp(),
        }

        with patch.object(
            auth_service.jwks_client, "get_signing_key_from_jwt", return_value=mock_signing_key
        ):
            with patch("jwt.decode", return_value=valid_payload):
                result = await auth_service.validate_token("Bearer valid.jwt.token")

                assert result is not None
                assert result["sub"] == "user-123"
                assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_validate_token_expired(self, auth_service_with_mock_db):
        """Test token validation with expired token."""
        auth_service = auth_service_with_mock_db
        mock_signing_key = Mock()
        mock_signing_key.key = "test-key"

        with patch.object(
            auth_service.jwks_client, "get_signing_key_from_jwt", return_value=mock_signing_key
        ):
            with patch("jwt.decode", side_effect=jwt.ExpiredSignatureError()):
                result = await auth_service.validate_token("Bearer expired.jwt.token")

                assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_invalid_audience(self, auth_service_with_mock_db):
        """Test token validation with invalid audience."""
        auth_service = auth_service_with_mock_db
        mock_signing_key = Mock()
        mock_signing_key.key = "test-key"

        with patch.object(
            auth_service.jwks_client, "get_signing_key_from_jwt", return_value=mock_signing_key
        ):
            with patch("jwt.decode", side_effect=jwt.InvalidAudienceError()):
                result = await auth_service.validate_token("Bearer invalid.jwt.token")

                assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_invalid_signature(self, auth_service_with_mock_db):
        """Test token validation with invalid signature."""
        auth_service = auth_service_with_mock_db

        with patch.object(
            auth_service.jwks_client,
            "get_signing_key_from_jwt",
            side_effect=Exception("Invalid signature"),
        ):
            result = await auth_service.validate_token("Bearer invalid.jwt.token")

            assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_bearer_prefix_handling(self, auth_service_with_mock_db):
        """Test that Bearer prefix is properly handled."""
        auth_service = auth_service_with_mock_db
        mock_signing_key = Mock()
        mock_signing_key.key = "test-key"

        valid_payload = {"sub": "user-123", "email": "test@example.com"}

        with patch.object(
            auth_service.jwks_client, "get_signing_key_from_jwt", return_value=mock_signing_key
        ):
            with patch("jwt.decode", return_value=valid_payload) as mock_decode:
                # With Bearer prefix
                await auth_service.validate_token("Bearer test.jwt.token")
                called_token = mock_decode.call_args[0][0]
                assert not called_token.startswith("Bearer ")

                # Without Bearer prefix
                await auth_service.validate_token("test.jwt.token")
                result = await auth_service.validate_token("test.jwt.token")
                assert result is not None

    @pytest.mark.asyncio
    async def test_token_validation_with_all_required_claims(self, auth_service_with_mock_db):
        """Test that all required JWT claims are validated."""
        auth_service = auth_service_with_mock_db
        mock_signing_key = Mock()
        mock_signing_key.key = "test-key"

        # Token with all required claims
        valid_payload = {
            "sub": "user-123",
            "email": "test@example.com",
            "aud": "test-client-id",
            "iss": "https://login.microsoftonline.com/test-tenant-id/v2.0",
            "exp": datetime.now(UTC).timestamp() + 3600,
            "nbf": datetime.now(UTC).timestamp() - 60,
            "iat": datetime.now(UTC).timestamp(),
        }

        with patch.object(
            auth_service.jwks_client, "get_signing_key_from_jwt", return_value=mock_signing_key
        ):
            with patch("jwt.decode", return_value=valid_payload):
                result = await auth_service.validate_token("Bearer valid.jwt.token")

                assert result is not None
                assert "sub" in result
                assert "email" in result
                assert "aud" in result
                assert "iss" in result


class TestAuthServiceErrorHandling:
    """Test error handling in AuthService."""

    @pytest.fixture
    def auth_service(self):
        """Create auth service with mocked database."""
        db_service = InMemoryDatabaseService()
        with patch("src.auth.auth_service.Config") as mock_config:
            mock_config.return_value.get.side_effect = lambda key, default=None: {
                "AZURE_CLIENT_ID": "test-client-id",
                "AZURE_TENANT_ID": "test-tenant-id",
            }.get(key, default)
            return AuthService(database_service=db_service)

    @pytest.mark.asyncio
    async def test_validate_token_handles_expired_token(self, auth_service):
        """Test that expired tokens are rejected."""
        with patch.object(auth_service.jwks_client, "get_signing_key_from_jwt"):
            with patch("jwt.decode", side_effect=jwt.ExpiredSignatureError("Token expired")):
                result = await auth_service.validate_token("Bearer expired.jwt.token")
                assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_handles_invalid_audience(self, auth_service):
        """Test that tokens with wrong audience are rejected."""
        with patch.object(auth_service.jwks_client, "get_signing_key_from_jwt"):
            with patch("jwt.decode", side_effect=jwt.InvalidAudienceError("Invalid audience")):
                result = await auth_service.validate_token("Bearer wrong-aud.jwt.token")
                assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_handles_invalid_issuer(self, auth_service):
        """Test that tokens with wrong issuer are rejected."""
        with patch.object(auth_service.jwks_client, "get_signing_key_from_jwt"):
            with patch("jwt.decode", side_effect=jwt.InvalidIssuerError("Invalid issuer")):
                result = await auth_service.validate_token("Bearer wrong-iss.jwt.token")
                assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_handles_malformed_token(self, auth_service):
        """Test that malformed tokens are rejected."""
        with patch.object(auth_service.jwks_client, "get_signing_key_from_jwt"):
            with patch("jwt.decode", side_effect=jwt.InvalidTokenError("Malformed token")):
                result = await auth_service.validate_token("Bearer malformed.token")
                assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_handles_unexpected_errors(self, auth_service):
        """Test that unexpected errors during validation are handled."""
        with patch.object(
            auth_service.jwks_client,
            "get_signing_key_from_jwt",
            side_effect=Exception("Network error"),
        ):
            result = await auth_service.validate_token("Bearer valid.jwt.token")
            assert result is None

    @pytest.mark.asyncio
    async def test_validate_request_returns_error_when_no_auth_header(self, auth_service):
        """Test that missing Authorization header is handled."""
        mock_request = Mock()
        mock_request.headers = {}

        result = await auth_service.validate_request(mock_request)

        assert result.success is False
        assert "Missing Authorization header" in result.error_message

    @pytest.mark.asyncio
    async def test_validate_request_returns_error_when_token_invalid(self, auth_service):
        """Test that invalid tokens return error in validate_request."""
        mock_request = Mock()
        mock_request.headers = {"Authorization": "Bearer invalid.token"}

        with patch.object(auth_service, "validate_token", return_value=None):
            result = await auth_service.validate_request(mock_request)

            assert result.success is False
            assert "Invalid or expired token" in result.error_message

    @pytest.mark.asyncio
    async def test_validate_request_handles_exceptions(self, auth_service):
        """Test that exceptions during request validation are caught."""
        mock_request = Mock()
        mock_request.headers.get.side_effect = Exception("Unexpected error")

        result = await auth_service.validate_request(mock_request)

        assert result.success is False
        assert "Authentication validation failed" in result.error_message


class TestFakeAuthServiceBehavior:
    """Test the FakeAuthService test double for DI-based testing patterns."""

    @pytest.fixture
    async def db_service(self):
        """Create and initialize in-memory database service."""
        from tests.test_doubles import InMemoryDatabaseService

        service = InMemoryDatabaseService()
        await service.initialize()
        return service

    @pytest.fixture
    def fake_auth(self, db_service):
        """Create a FakeAuthService for testing."""
        from tests.test_doubles import FakeAuthService

        return FakeAuthService(database_service=db_service)

    @pytest.mark.asyncio
    async def test_fake_auth_validates_registered_tokens(self, fake_auth):
        """Test that FakeAuthService validates registered tokens."""
        claims = {"sub": "user-123", "email": "test@example.com", "name": "Test User"}
        fake_auth.add_valid_token("valid-token-abc", claims)

        result = await fake_auth.validate_token("valid-token-abc")

        assert result is not None
        assert result["sub"] == "user-123"
        assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_fake_auth_rejects_unregistered_tokens(self, fake_auth):
        """Test that FakeAuthService rejects unregistered tokens."""
        result = await fake_auth.validate_token("unknown-token")

        assert result is None

    @pytest.mark.asyncio
    async def test_fake_auth_validate_request_extracts_bearer_token(self, fake_auth):
        """Test that validate_request correctly extracts and validates bearer token."""
        claims = {"sub": "user-456", "email": "bearer@example.com"}
        fake_auth.add_valid_token("my-bearer-token", claims)

        mock_request = Mock()
        mock_request.headers = {"Authorization": "Bearer my-bearer-token"}

        result = await fake_auth.validate_request(mock_request)

        assert result.success is True
        assert result.user_claims is not None
        assert result.user_claims["sub"] == "user-456"

    @pytest.mark.asyncio
    async def test_fake_auth_validate_request_fails_without_bearer_prefix(self, fake_auth):
        """Test that validate_request requires Bearer prefix."""
        mock_request = Mock()
        mock_request.headers = {"Authorization": "my-token"}

        result = await fake_auth.validate_request(mock_request)

        assert result.success is False
        assert "Missing or invalid Authorization header" in result.error_message

    @pytest.mark.asyncio
    async def test_fake_auth_get_or_create_creates_new_user(self, fake_auth, db_service):
        """Test that get_or_create_user creates a new user in database."""
        token_payload = {"sub": "new-user-id", "email": "new@example.com", "name": "New User"}

        result = await fake_auth.get_or_create_user(token_payload)

        assert result is not None
        user, is_new = result
        assert is_new is True
        assert user.id == "new-user-id"
        assert user.email == "new@example.com"

        # Verify user exists in database
        db_user = await db_service.get_user_by_id("new-user-id")
        assert db_user is not None

    @pytest.mark.asyncio
    async def test_fake_auth_get_or_create_returns_existing_user(self, fake_auth, db_service):
        """Test that get_or_create_user returns existing user."""
        # Pre-create user in database
        await db_service.create_user(
            {
                "id": "existing-id",
                "email": "existing@example.com",
                "name": "Existing User",
                "roles": ["user", "premium"],
            }
        )

        token_payload = {"sub": "existing-id", "email": "existing@example.com"}

        result = await fake_auth.get_or_create_user(token_payload)

        assert result is not None
        user, is_new = result
        assert is_new is False
        assert user.id == "existing-id"

    @pytest.mark.asyncio
    async def test_fake_auth_configurable_failure_mode(self, fake_auth):
        """Test that FakeAuthService can be configured to fail all validations."""
        claims = {"sub": "user-123"}
        fake_auth.add_valid_token("valid-token", claims)

        # Enable failure mode
        fake_auth.set_validation_failure(True, "Simulated auth failure")

        result = await fake_auth.validate_token("valid-token")
        assert result is None

        # Validate request also fails
        mock_request = Mock()
        mock_request.headers = {"Authorization": "Bearer valid-token"}

        auth_result = await fake_auth.validate_request(mock_request)
        assert auth_result.success is False
        assert "Simulated auth failure" in auth_result.error_message

        # Disable failure mode
        fake_auth.set_validation_failure(False)
        result = await fake_auth.validate_token("valid-token")
        assert result is not None
