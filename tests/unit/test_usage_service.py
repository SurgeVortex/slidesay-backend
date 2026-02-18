import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from src.services.usage_service import UsageService

@pytest.fixture
def cosmos_mock():
    cosmos = MagicMock()
    cosmos.get_container_client.return_value = MagicMock()
    cosmos._execute_operation = AsyncMock()
    return cosmos

@pytest.fixture
def usage_service(cosmos_mock):
    return UsageService(cosmos_mock)

def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

def make_usage(user_id, month=None, presentationsCreated=0, exportsUsed=0, tier="free"):
    if not month:
        from datetime import datetime, timezone
        month = datetime.now(timezone.utc).strftime("%Y-%m")
    return {
        "id": f"{user_id}:{month}",
        "userId": user_id,
        "month": month,
        "presentationsCreated": presentationsCreated,
        "exportsUsed": exportsUsed,
        "tier": tier,
    }

def test_get_usage_new_user(usage_service, cosmos_mock):
    # Simulate not found
    cosmos_mock._execute_operation.side_effect = Exception("Not found")
    usage = run_async(usage_service.get_usage("alice"))
    assert usage["presentationsCreated"] == 0
    assert usage["exportsUsed"] == 0
    assert usage["tier"] == "free"

def test_can_create_free_under_limit(usage_service, cosmos_mock):
    cosmos_mock._execute_operation.return_value = make_usage("bob", presentationsCreated=3)
    allowed, reason = run_async(usage_service.can_create_presentation("bob"))
    assert allowed
    assert reason == "ok"

def test_can_create_free_at_limit(usage_service, cosmos_mock):
    cosmos_mock._execute_operation.return_value = make_usage("claire", presentationsCreated=5)
    allowed, reason = run_async(usage_service.can_create_presentation("claire"))
    assert not allowed
    assert "limit" in reason

def test_can_create_educator(usage_service, cosmos_mock):
    cosmos_mock._execute_operation.return_value = make_usage("dave", presentationsCreated=42, tier="educator")
    allowed, reason = run_async(usage_service.can_create_presentation("dave"))
    assert allowed
    assert reason == "ok"

def test_can_export_free(usage_service, cosmos_mock):
    cosmos_mock._execute_operation.return_value = make_usage("eve", tier="free")
    allowed, reason = run_async(usage_service.can_export("eve"))
    assert not allowed
    assert "Export is available" in reason

def test_can_export_educator(usage_service, cosmos_mock):
    cosmos_mock._execute_operation.return_value = make_usage("frank", tier="educator")
    allowed, reason = run_async(usage_service.can_export("frank"))
    assert allowed
    assert reason == "ok"

def test_record_presentation(usage_service, cosmos_mock):
    cosmos_mock._execute_operation.return_value = make_usage("gabe", presentationsCreated=1)
    usage = run_async(usage_service.record_presentation_created("gabe"))
    assert usage["presentationsCreated"] == 2

def test_record_export(usage_service, cosmos_mock):
    cosmos_mock._execute_operation.return_value = make_usage("hal", exportsUsed=1)
    usage = run_async(usage_service.record_export("hal"))
    assert usage["exportsUsed"] == 2

def test_set_tier(usage_service, cosmos_mock):
    cosmos_mock._execute_operation.return_value = make_usage("ivy", tier="free")
    usage = run_async(usage_service.set_tier("ivy", "pro"))
    assert usage["tier"] == "pro"

def test_set_invalid_tier(usage_service, cosmos_mock):
    with pytest.raises(ValueError):
        run_async(usage_service.set_tier("jack", "unknown"))
