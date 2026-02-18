"""
Configuration Management

Handles environment variables and application configuration.
"""

import os
from typing import Any


class Config:
    """Configuration manager for environment variables and settings."""

    def __init__(self) -> None:
        """Initialize configuration with environment variables."""
        self._config = dict(os.environ)

        # Set default values
        self._defaults = {
            "ENVIRONMENT": "development",
            "LOG_LEVEL": "INFO",
            "APP_NAME": "saas-backend-template",
            "APP_VERSION": "1.0.0",
            "PYTHON_ISOLATE_WORKER_DEPENDENCIES": "1",
            "FUNCTIONS_WORKER_RUNTIME": "python",
            "FUNCTIONS_EXTENSION_VERSION": "~4",
            # Cosmos DB defaults
            "COSMOS_DB_DATABASE": "saas_template",
            "COSMOS_DB_CONTAINER_USERS": "users",
            "COSMOS_DB_CONTAINER_DATA": "user_data",
            # Monitoring defaults
            "ENABLE_METRICS_BUFFERING": "true",
            "METRICS_BUFFER_SIZE": "100",
            "METRICS_FLUSH_INTERVAL_SECONDS": "30",
            # Rate limiting defaults
            "RATE_LIMIT_DEFAULT_PER_MINUTE": "60",
            "RATE_LIMIT_DEFAULT_PER_HOUR": "1000",
            # JWT defaults
            "JWT_ALGORITHM": "HS256",
            "JWT_EXPIRATION_HOURS": "24",
            # Redis defaults
            "RATE_LIMIT_REDIS_URL": "redis://localhost:6379",
        }

    def get(self, key: str, default: str | None = None) -> str | None:
        """
        Get a configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self._config.get(key, self._defaults.get(key, default))

    def get_int(self, key: str, default: int = 0) -> int:
        """Get an integer configuration value."""
        value = self.get(key)
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get a float configuration value."""
        value = self.get(key)
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get a boolean configuration value."""
        value = self.get(key)
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "on")

    def get_list(self, key: str, separator: str = ",", default: list | None = None) -> list:
        """Get a list configuration value."""
        value = self.get(key)
        if value is None:
            return default or []
        return [item.strip() for item in value.split(separator) if item.strip()]

    def set(self, key: str, value: str) -> None:
        """Set a configuration value."""
        self._config[key] = value

    def is_development(self) -> bool:
        """Check if running in development environment."""
        env = self.get("ENVIRONMENT", "development")
        return env.lower() == "development" if env else True

    def is_production(self) -> bool:
        """Check if running in production environment."""
        env = self.get("ENVIRONMENT", "development")
        return env.lower() == "production" if env else False

    def get_database_config(self) -> dict[str, Any]:
        """Get database configuration."""
        return {
            "endpoint": self.get("COSMOS_DB_ENDPOINT"),
            "key": self.get("COSMOS_DB_KEY"),
            "database": self.get("COSMOS_DB_DATABASE"),
            "containers": {
                "users": self.get("COSMOS_DB_CONTAINER_USERS"),
                "user_data": self.get("COSMOS_DB_CONTAINER_DATA"),
            },
        }

    def get_auth_config(self) -> dict[str, Any]:
        """Get authentication configuration."""
        return {
            "jwt_secret": self.get("JWT_SECRET_KEY"),
            "jwt_algorithm": self.get("JWT_ALGORITHM"),
            "jwt_expiration_hours": self.get_int("JWT_EXPIRATION_HOURS"),
            "azure_client_id": self.get("AZURE_CLIENT_ID"),
            "azure_tenant_id": self.get("AZURE_TENANT_ID"),
        }

    def get_monitoring_config(self) -> dict[str, Any]:
        """Get monitoring configuration."""
        return {
            "grafana_url": self.get("GRAFANA_CLOUD_URL"),
            "grafana_api_key": self.get("GRAFANA_CLOUD_API_KEY"),
            "grafana_user_id": self.get("GRAFANA_CLOUD_USER_ID"),
            "enable_buffering": self.get_bool("ENABLE_METRICS_BUFFERING"),
            "buffer_size": self.get_int("METRICS_BUFFER_SIZE"),
            "flush_interval": self.get_int("METRICS_FLUSH_INTERVAL_SECONDS"),
        }

    def get_rate_limit_config(self) -> dict[str, Any]:
        """Get rate limiting configuration."""
        return {
            "redis_url": self.get("RATE_LIMIT_REDIS_URL"),
            "default_per_minute": self.get_int("RATE_LIMIT_DEFAULT_PER_MINUTE"),
            "default_per_hour": self.get_int("RATE_LIMIT_DEFAULT_PER_HOUR"),
        }

    def validate_required_config(self) -> dict[str, list]:
        """
        Validate that required configuration is present.

        Returns:
            Dictionary with 'missing' and 'invalid' keys containing lists of issues
        """
        missing = []
        invalid = []

        # Required for production
        if self.is_production():
            required_keys = [
                "COSMOS_DB_ENDPOINT",
                "COSMOS_DB_KEY",
                "JWT_SECRET_KEY",
                "AZURE_CLIENT_ID",
                "AZURE_TENANT_ID",
            ]

            for key in required_keys:
                if not self.get(key):
                    missing.append(key)

        # Validate Cosmos DB endpoint format
        cosmos_endpoint = self.get("COSMOS_DB_ENDPOINT")
        if cosmos_endpoint and not cosmos_endpoint.startswith(("https://", "http://")):
            invalid.append("COSMOS_DB_ENDPOINT must be a valid URL")

        # Validate Grafana URL format
        grafana_url = self.get("GRAFANA_CLOUD_URL")
        if grafana_url and not grafana_url.startswith(("https://", "http://")):
            invalid.append("GRAFANA_CLOUD_URL must be a valid URL")

        # Validate numeric values
        try:
            self.get_int("JWT_EXPIRATION_HOURS")
        except ValueError:
            invalid.append("JWT_EXPIRATION_HOURS must be a valid integer")

        return {"missing": missing, "invalid": invalid}

    def get_all_config(self, include_secrets: bool = False) -> dict[str, str]:
        """
        Get all configuration values.

        Args:
            include_secrets: Whether to include sensitive values

        Returns:
            Dictionary of all configuration
        """
        if include_secrets:
            return dict(self._config)

        # Filter out sensitive keys
        sensitive_keys = {
            "COSMOS_DB_KEY",
            "JWT_SECRET_KEY",
            "GRAFANA_CLOUD_API_KEY",
            "AZURE_CLIENT_SECRET",
        }

        filtered_config = {}
        for key, value in self._config.items():
            if key in sensitive_keys:
                filtered_config[key] = "*" * 8
            else:
                filtered_config[key] = value

        return filtered_config
