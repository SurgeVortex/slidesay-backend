"""Authentication service for Microsoft Entra External ID OAuth2.

The backend validates OAuth2 access tokens from the frontend, which uses
Microsoft Entra External ID (Public Client flow). After validation, the backend
ensures the user exists in Cosmos DB and manages their profile.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import jwt
from azure.functions import HttpRequest
from jwt import PyJWKClient

from src.interfaces.auth_interface import AuthResult, IAuthService
from src.interfaces.database_interface import IDatabaseService
from src.utils.config import Config
from src.utils.logger import get_logger


@dataclass
class User:
    """Represents a user in our system."""

    id: str
    email: str
    name: str
    display_name: str
    roles: list[str]
    created_at: datetime
    last_login: datetime
    is_active: bool = True


class AuthService(IAuthService):
    """Authentication service for Microsoft Entra External ID OAuth2."""

    def __init__(self, database_service: IDatabaseService):
        self.config = Config()
        self.logger = get_logger(__name__)
        self.database_service = database_service

        # Microsoft Entra configuration
        self.client_id = self.config.get("AZURE_CLIENT_ID")
        self.tenant_id = self.config.get("AZURE_TENANT_ID")

        if not self.client_id or not self.tenant_id:
            raise ValueError("AZURE_CLIENT_ID and AZURE_TENANT_ID are required for authentication")

        # OpenID Connect endpoints
        self.issuer = f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"
        self.jwks_url = f"https://login.microsoftonline.com/{self.tenant_id}/discovery/v2.0/keys"

        # JWT validation client
        self.jwks_client = PyJWKClient(self.jwks_url)

        # Default roles for new users
        self.default_roles = ["user"]
        admin_emails_str = self.config.get("ADMIN_EMAILS", "")
        self.admin_emails = admin_emails_str.split(",") if admin_emails_str else []

    async def validate_token(self, token: str) -> dict[str, Any] | None:
        """
        Validate an OAuth2 access token from Microsoft Entra External ID.
        Args:
            token: The Bearer token from the Authorization header
        Returns:
            Decoded token payload if valid, None otherwise
        """
        try:
            # Remove 'Bearer ' prefix if present
            if token.startswith("Bearer "):
                token = token[7:]

            # Get the signing key from JWKS
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)

            # Decode and validate the token
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=self.issuer,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )

            # jwt.decode returns Any; convert to a plain dict to satisfy typing
            return dict(payload)

        except jwt.ExpiredSignatureError:
            self.logger.warning("Token has expired")
            return None
        except jwt.InvalidAudienceError:
            self.logger.warning("Invalid token audience")
            return None
        except jwt.InvalidIssuerError:
            self.logger.warning("Invalid token issuer")
            return None
        except jwt.InvalidTokenError as e:
            self.logger.warning("Invalid token", error=str(e))
            return None
        except Exception as e:
            self.logger.error("Token validation error", error=str(e))
            return None

    async def validate_request(self, request: HttpRequest) -> AuthResult:
        """
        Validate an Azure Functions HTTP request with Bearer token.
        Args:
            request: Azure Functions HttpRequest object
        Returns:
            AuthResult with validation status and user claims
        """
        try:
            # Get Authorization header
            auth_header = request.headers.get("Authorization")

            if not auth_header:
                return AuthResult(success=False, error_message="Missing Authorization header")

            # Validate token
            token_payload = await self.validate_token(auth_header)

            if not token_payload:
                return AuthResult(success=False, error_message="Invalid or expired token")

            return AuthResult(success=True, user_claims=token_payload)

        except Exception as e:
            self.logger.error("Request validation error", error=str(e))
            return AuthResult(success=False, error_message="Authentication validation failed")

    async def get_or_create_user(
        self,
        token_payload: dict[str, Any],
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[User, bool] | None:
        """
        Get existing user or create new user from token claims.
        Args:
            token_payload: Validated JWT token payload
            ip_address: Client IP address for audit logging
            user_agent: Client user agent for audit logging
        Returns:
            Tuple of (User object, is_new_user flag) if successful, None otherwise
        """
        try:
            # Extract user information from token
            user_id = token_payload.get("sub")  # Subject claim (unique user ID)
            email = token_payload.get("email") or token_payload.get("preferred_username")
            name = token_payload.get("name", "")
            given_name = token_payload.get("given_name", "")
            family_name = token_payload.get("family_name", "")

            if not user_id:
                self.logger.error("No user ID (sub claim) in token payload")
                return None

            if not email:
                self.logger.error("No email in token payload")
                return None

            # Construct display name
            if name:
                display_name = name
            elif given_name or family_name:
                display_name = f"{given_name} {family_name}".strip()
            else:
                display_name = email.split("@")[0]

            # Try to get existing user
            user_dict = await self._get_user_by_id(user_id)

            if user_dict:
                # Update last login
                await self._update_last_login(user_id)

                # Log successful login to audit
                await self._log_audit(
                    user_id,
                    "user_login",
                    {"email": user_dict.get("email"), "action": "successful_login"},
                    ip_address,
                    user_agent,
                )

                # Convert dict to User object
                user = User(
                    id=user_dict["id"],
                    email=user_dict["email"],
                    name=user_dict.get("name", ""),
                    display_name=user_dict.get("displayName", ""),
                    roles=user_dict.get("roles", []),
                    created_at=datetime.fromisoformat(user_dict["createdAt"]),
                    last_login=datetime.fromisoformat(
                        user_dict.get("lastLoginAt", user_dict["createdAt"])
                    ),
                    is_active=user_dict.get("isActive", True),
                )

                return (user, False)  # Existing user, not new

            # Create new user
            # Determine roles
            roles = self.default_roles.copy()
            if email in self.admin_emails:
                roles.append("admin")

            now = datetime.now(UTC)

            user_data = {
                "id": user_id,
                "userId": user_id,  # Required: partition key field
                "email": email,
                "name": name or display_name,
                "displayName": display_name,
                "roles": roles,
                "createdAt": now.isoformat(),
                "lastLoginAt": now.isoformat(),
                "isActive": True,
            }

            # Save to database
            await self.database_service.create_user(user_data)

            # Log to audit
            await self._log_audit(
                user_id,
                "user_created",
                {"email": email, "display_name": display_name},
                ip_address,
                user_agent,
            )

            user = User(
                id=user_data["id"],
                email=user_data["email"],
                name=user_data["name"],
                display_name=user_data["displayName"],
                roles=user_data["roles"],
                created_at=now,
                last_login=now,
                is_active=user_data["isActive"],
            )

            self.logger.info("Created new user", user_id=user.id, email=user.email)
            return (user, True)  # New user created

        except Exception as e:
            self.logger.error("Failed to get or create user", error=str(e))
            return None

    def has_role(self, user: User, required_role: str) -> bool:
        """Check if user has the required role."""
        return required_role in user.roles

    def has_any_role(self, user: User, required_roles: list[str]) -> bool:
        """Check if user has any of the required roles."""
        return any(role in user.roles for role in required_roles)

    async def _get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """Get user by ID using userId as partition key."""
        try:
            return await self.database_service.get_user_by_id(user_id)
        except Exception as e:
            self.logger.error("Failed to get user", user_id=user_id, error=str(e))
            return None

    async def _update_last_login(self, user_id: str) -> None:
        """Update user's last login timestamp."""
        try:
            await self.database_service.update_user(
                user_id=user_id, updates={"lastLoginAt": datetime.now(UTC).isoformat()}
            )
        except Exception as e:
            self.logger.error("Failed to update last login", user_id=user_id, error=str(e))

    async def _log_audit(
        self,
        user_id: str,
        action: str,
        metadata: dict[str, Any],
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Log an action to the audit container."""
        try:
            import uuid

            audit_data = {
                "id": str(uuid.uuid4()),
                "userId": user_id,
                "action": action,
                "timestamp": datetime.now(UTC).isoformat(),
                "metadata": metadata,
                "ipAddress": ip_address or "unknown",
                "userAgent": user_agent or "unknown",
            }

            # Save to audit logs container
            await self.database_service.create_audit_log(audit_data)

        except Exception as e:
            self.logger.error("Failed to log audit", error=str(e), user_id=user_id, action=action)
