"""Tests for admin tier override endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.usage_service import UsageService


class TestUsageServiceSetTier:
    """Test the set_tier method on UsageService."""

    @pytest.fixture
    def mock_cosmos(self):
        cosmos = MagicMock()
        container_client = MagicMock()
        container_client.upsert_item = AsyncMock()
        container_client.read_item = AsyncMock(
            return_value={
                "id": "user1:2026-02",
                "userId": "user1",
                "month": "2026-02",
                "presentationsCreated": 0,
                "exportsUsed": 0,
                "tier": "free",
            }
        )
        cosmos.get_container_client = MagicMock(return_value=container_client)

        async def execute_op(name, fn, **kwargs):
            result = fn(**kwargs)
            if hasattr(result, "__await__"):
                return await result
            return result

        cosmos._execute_operation = AsyncMock(side_effect=execute_op)
        return cosmos

    @pytest.mark.asyncio
    async def test_set_tier_to_educator(self, mock_cosmos):
        svc = UsageService(mock_cosmos)
        result = await svc.set_tier("user1", "educator")
        assert result["tier"] == "educator"

    @pytest.mark.asyncio
    async def test_set_tier_to_pro(self, mock_cosmos):
        svc = UsageService(mock_cosmos)
        result = await svc.set_tier("user1", "pro")
        assert result["tier"] == "pro"

    @pytest.mark.asyncio
    async def test_set_tier_to_free(self, mock_cosmos):
        svc = UsageService(mock_cosmos)
        result = await svc.set_tier("user1", "free")
        assert result["tier"] == "free"

    @pytest.mark.asyncio
    async def test_set_invalid_tier_raises(self, mock_cosmos):
        svc = UsageService(mock_cosmos)
        with pytest.raises(ValueError, match="Invalid tier"):
            await svc.set_tier("user1", "enterprise")


class TestIsAdmin:
    """Test admin check function."""

    def test_admin_user(self):
        from src.functions.http_functions import _is_admin
        with patch.dict("os.environ", {"ADMIN_USER_IDS": "admin1,admin2"}):
            assert _is_admin("admin1") is True
            assert _is_admin("admin2") is True

    def test_non_admin_user(self):
        from src.functions.http_functions import _is_admin
        with patch.dict("os.environ", {"ADMIN_USER_IDS": "admin1,admin2"}):
            assert _is_admin("regular_user") is False

    def test_no_admins_configured(self):
        from src.functions.http_functions import _is_admin
        with patch.dict("os.environ", {"ADMIN_USER_IDS": ""}):
            assert _is_admin("anyone") is False

    def test_whitespace_handling(self):
        from src.functions.http_functions import _is_admin
        with patch.dict("os.environ", {"ADMIN_USER_IDS": " admin1 , admin2 "}):
            assert _is_admin("admin1") is True
