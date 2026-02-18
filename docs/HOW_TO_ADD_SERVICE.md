# How to Add a New Service

This guide walks through adding a new service to the backend. We'll use creating a "Notification Service" as an example.

## Architecture Overview

Services in this codebase follow an interface-driven architecture:

```text
src/interfaces/notification_interface.py  ← Contract (what it does)
src/notifications/notification_service.py ← Implementation (how it works)
src/container.py                          ← Registration (how to get it)
tests/test_doubles.py                     ← Fake for testing
```

## Step 1: Define the Interface

Create the interface in `src/interfaces/`:

```python
# src/interfaces/notification_interface.py
"""
Notification Service Interface.

Defines the contract for notification services.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class NotificationChannel(Enum):
    """Supported notification channels."""
    EMAIL = "email"
    PUSH = "push"
    IN_APP = "in_app"


@dataclass
class Notification:
    """Notification data structure."""
    id: str
    user_id: str
    channel: NotificationChannel
    title: str
    body: str
    sent_at: str | None = None
    read_at: str | None = None


class INotificationService(ABC):
    """Interface for notification services."""

    @abstractmethod
    async def send_notification(
        self,
        user_id: str,
        channel: NotificationChannel,
        title: str,
        body: str,
        metadata: dict | None = None
    ) -> Notification:
        """
        Send a notification to a user.

        Args:
            user_id: Target user ID
            channel: Notification channel (email, push, in_app)
            title: Notification title
            body: Notification body
            metadata: Optional additional data

        Returns:
            Created notification record

        Raises:
            NotificationError: If sending fails
        """
        pass

    @abstractmethod
    async def get_notifications(
        self,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50
    ) -> list[Notification]:
        """
        Get notifications for a user.

        Args:
            user_id: User ID to get notifications for
            unread_only: If True, only return unread notifications
            limit: Maximum notifications to return

        Returns:
            List of notifications
        """
        pass

    @abstractmethod
    async def mark_as_read(self, notification_id: str, user_id: str) -> bool:
        """
        Mark a notification as read.

        Args:
            notification_id: Notification ID to mark
            user_id: User ID (for authorization)

        Returns:
            True if marked, False if not found
        """
        pass
```

## Step 2: Export from Interfaces Package

Add to `src/interfaces/__init__.py`:

```python
# src/interfaces/__init__.py

# ... existing exports ...

from src.interfaces.notification_interface import (
    INotificationService,
    Notification,
    NotificationChannel,
)

__all__ = [
    # ... existing exports ...
    "INotificationService",
    "Notification",
    "NotificationChannel",
]
```

## Step 3: Create the Implementation

Create the service implementation:

```python
# src/notifications/__init__.py
"""Notification service module."""
```

```python
# src/notifications/notification_service.py
"""
Notification Service Implementation.

Handles sending and managing user notifications.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.interfaces.notification_interface import (
    INotificationService,
    Notification,
    NotificationChannel,
)

if TYPE_CHECKING:
    from src.interfaces import IDatabaseService


class NotificationError(Exception):
    """Raised when notification operations fail."""
    pass


class NotificationService(INotificationService):
    """
    Notification service implementation.

    Stores notifications in Cosmos DB and (optionally) sends
    via external channels (email, push).
    """

    def __init__(self, database_service: "IDatabaseService"):
        """
        Initialize notification service.

        Args:
            database_service: Database service for persistence
        """
        self.database_service = database_service
        self._container_name = "notifications"

    async def send_notification(
        self,
        user_id: str,
        channel: NotificationChannel,
        title: str,
        body: str,
        metadata: dict | None = None
    ) -> Notification:
        """Send a notification to a user."""
        notification_id = f"notif-{uuid.uuid4()}"
        now = datetime.now(timezone.utc).isoformat()

        notification_data = {
            "id": notification_id,
            "userId": user_id,  # Partition key
            "channel": channel.value,
            "title": title,
            "body": body,
            "sentAt": now,
            "readAt": None,
            "metadata": metadata or {},
            "createdAt": now,
        }

        # Store in database
        result = await self.database_service.query_items(
            container_name=self._container_name,
            query="SELECT * FROM c WHERE false",  # Placeholder - use create operation
            partition_key=user_id
        )

        # In real implementation, use container client to create item
        container = self.database_service.get_container_client(self._container_name)
        await container.create_item(notification_data)

        # TODO: Send via external channel (email, push) based on channel type
        # For now, just store in database for in-app notifications

        return Notification(
            id=notification_id,
            user_id=user_id,
            channel=channel,
            title=title,
            body=body,
            sent_at=now,
        )

    async def get_notifications(
        self,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50
    ) -> list[Notification]:
        """Get notifications for a user."""
        query = "SELECT * FROM c WHERE c.userId = @userId"
        params = [{"name": "@userId", "value": user_id}]

        if unread_only:
            query += " AND c.readAt = null"

        query += " ORDER BY c.sentAt DESC"

        results = await self.database_service.query_items(
            container_name=self._container_name,
            query=query,
            parameters=params,
            partition_key=user_id
        )

        return [
            Notification(
                id=r["id"],
                user_id=r["userId"],
                channel=NotificationChannel(r["channel"]),
                title=r["title"],
                body=r["body"],
                sent_at=r.get("sentAt"),
                read_at=r.get("readAt"),
            )
            for r in results[:limit]
        ]

    async def mark_as_read(self, notification_id: str, user_id: str) -> bool:
        """Mark a notification as read."""
        # Query to verify ownership
        results = await self.database_service.query_items(
            container_name=self._container_name,
            query="SELECT * FROM c WHERE c.id = @id AND c.userId = @userId",
            parameters=[
                {"name": "@id", "value": notification_id},
                {"name": "@userId", "value": user_id},
            ],
            partition_key=user_id
        )

        if not results:
            return False

        # Update with readAt timestamp
        container = self.database_service.get_container_client(self._container_name)
        now = datetime.now(timezone.utc).isoformat()

        notification = results[0]
        notification["readAt"] = now

        await container.upsert_item(notification)
        return True
```

## Step 4: Register in Container

Add to `src/container.py`:

```python
# src/container.py

from src.interfaces import (
    # ... existing imports ...
    INotificationService,
)


class ServiceContainer:
    def __init__(self) -> None:
        # ... existing fields ...
        self._notification_service: INotificationService | None = None

    # ... existing methods ...

    def get_notification_service(self) -> INotificationService:
        """Get notification service (singleton)."""
        if self._notification_service is None:
            from src.notifications.notification_service import NotificationService

            self._notification_service = NotificationService(
                database_service=self.get_database_service()
            )
        return self._notification_service

    def reset(self) -> None:
        """Reset all services (useful for testing)."""
        # ... existing resets ...
        self._notification_service = None
```

## Step 5: Create Test Doubles

Add a fake implementation in `tests/test_doubles.py`:

```python
# tests/test_doubles.py

from src.interfaces.notification_interface import (
    INotificationService,
    Notification,
    NotificationChannel,
)


class FakeNotificationService(INotificationService):
    """Fake notification service for testing."""

    def __init__(self):
        self.notifications: dict[str, list[Notification]] = {}
        self.send_calls: list[dict] = []

    async def send_notification(
        self,
        user_id: str,
        channel: NotificationChannel,
        title: str,
        body: str,
        metadata: dict | None = None
    ) -> Notification:
        """Record the call and store notification in memory."""
        self.send_calls.append({
            "user_id": user_id,
            "channel": channel,
            "title": title,
            "body": body,
            "metadata": metadata,
        })

        notification = Notification(
            id=f"fake-notif-{len(self.send_calls)}",
            user_id=user_id,
            channel=channel,
            title=title,
            body=body,
            sent_at="2025-01-01T00:00:00Z",
        )

        if user_id not in self.notifications:
            self.notifications[user_id] = []
        self.notifications[user_id].append(notification)

        return notification

    async def get_notifications(
        self,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50
    ) -> list[Notification]:
        """Return stored notifications for user."""
        user_notifs = self.notifications.get(user_id, [])
        if unread_only:
            user_notifs = [n for n in user_notifs if n.read_at is None]
        return user_notifs[:limit]

    async def mark_as_read(self, notification_id: str, user_id: str) -> bool:
        """Mark notification as read in memory."""
        for notif in self.notifications.get(user_id, []):
            if notif.id == notification_id:
                notif.read_at = "2025-01-01T00:00:01Z"
                return True
        return False

    def reset(self):
        """Clear all state."""
        self.notifications.clear()
        self.send_calls.clear()
```

## Step 6: Write Tests

Create test file for the service:

```python
# tests/test_notification_service.py

import pytest
from src.notifications.notification_service import NotificationService
from src.interfaces import NotificationChannel
from tests.test_doubles import FakeDatabaseService


class TestNotificationService:
    """Tests for NotificationService."""

    @pytest.fixture
    def fake_db(self):
        """Create fake database service."""
        return FakeDatabaseService()

    @pytest.fixture
    def service(self, fake_db):
        """Create notification service with fake dependencies."""
        return NotificationService(database_service=fake_db)

    @pytest.mark.asyncio
    async def test_send_notification_creates_record(self, service, fake_db):
        """Test that sending notification creates database record."""
        # Arrange
        user_id = "user-123"

        # Act
        notification = await service.send_notification(
            user_id=user_id,
            channel=NotificationChannel.IN_APP,
            title="Welcome!",
            body="Thanks for signing up."
        )

        # Assert
        assert notification.id.startswith("notif-")
        assert notification.user_id == user_id
        assert notification.title == "Welcome!"
        assert notification.sent_at is not None

    @pytest.mark.asyncio
    async def test_get_notifications_filters_by_user(self, service):
        """Test that notifications are filtered by user ID."""
        # Send notifications to different users
        await service.send_notification("user-1", NotificationChannel.IN_APP, "A", "Body A")
        await service.send_notification("user-2", NotificationChannel.IN_APP, "B", "Body B")

        # Get for user-1 only
        notifications = await service.get_notifications("user-1")

        # Should only see user-1's notification
        assert all(n.user_id == "user-1" for n in notifications)

    @pytest.mark.asyncio
    async def test_mark_as_read_updates_timestamp(self, service):
        """Test marking notification as read."""
        notification = await service.send_notification(
            "user-123",
            NotificationChannel.IN_APP,
            "Test",
            "Body"
        )

        result = await service.mark_as_read(notification.id, "user-123")

        assert result is True

    @pytest.mark.asyncio
    async def test_mark_as_read_fails_for_wrong_user(self, service):
        """Test that users can't mark others' notifications as read."""
        notification = await service.send_notification(
            "user-123",
            NotificationChannel.IN_APP,
            "Test",
            "Body"
        )

        # Try to mark as read as different user
        result = await service.mark_as_read(notification.id, "user-456")

        assert result is False
```

## Step 7: Add to mypy Configuration

If your service has special typing needs, add to `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = "src.notifications.*"
disallow_untyped_defs = true
```

## Step 8: Run Checks

```bash
# Ensure everything passes
make checks
make test
```

## Checklist

Before considering the service complete:

- [ ] Interface defined in `src/interfaces/`
- [ ] Interface exported from `src/interfaces/__init__.py`
- [ ] Implementation created in `src/<service_name>/`
- [ ] Implementation uses dependency injection (receives dependencies in `__init__`)
- [ ] Registered in `container.py` with lazy loading
- [ ] Fake/mock created in `tests/test_doubles.py`
- [ ] Unit tests written
- [ ] Tests verify tenant isolation (user ID filtering)
- [ ] `make checks` passes
- [ ] `make test` passes

## Advanced Patterns

### Service with External Dependencies

For services that call external APIs:

```python
class ExternalApiService(IExternalApiService):
    def __init__(self, http_client: httpx.AsyncClient, config: Config):
        self.http_client = http_client
        self.api_key = config.get("EXTERNAL_API_KEY")
        self.base_url = config.get("EXTERNAL_API_URL")
```

### Service with Caching

```python
class CachedDataService(IDataService):
    def __init__(self, database: IDatabaseService):
        self.database = database
        self._cache: dict[str, Any] = {}
        self._cache_ttl = 300  # 5 minutes

    async def get_data(self, key: str) -> Any:
        if key in self._cache:
            return self._cache[key]

        data = await self.database.get(key)
        self._cache[key] = data
        return data
```

### Service that Creates Audit Logs

```python
class AuditableService(IAuditableService):
    def __init__(
        self,
        database: IDatabaseService,
        monitor_factory: Callable[[], IMonitoringService]
    ):
        self.database = database
        self.monitor_factory = monitor_factory

    async def perform_action(self, user_id: str, action_data: dict) -> Result:
        monitor = self.monitor_factory()

        result = await self._do_action(action_data)

        await monitor.create_audit_log(
            user_id=user_id,
            action="perform_action",
            resource="/api/actions",
            method="POST",
            status_code=200,
            metadata=action_data
        )

        return result
```
