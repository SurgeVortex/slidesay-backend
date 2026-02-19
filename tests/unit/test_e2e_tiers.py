import asyncio
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.usage_service import UsageService

def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

def make_usage(user_id, month=None, presentationsCreated=0, exportsUsed=0, tier="free"):
    if not month:
        from datetime import datetime
        month = datetime.now(UTC).strftime("%Y-%m")
    return {
        "id": f"{user_id}:{month}",
        "userId": user_id,
        "month": month,
        "presentationsCreated": presentationsCreated,
        "exportsUsed": exportsUsed,
        "tier": tier,
    }

@pytest.mark.asyncio
async def test_e2e_tier_usage_blocks_on_free_limits():
    mock_cosmos = MagicMock()
    svc = UsageService(mock_cosmos)
    
    mock_cosmos._execute_operation = AsyncMock()
    # Start as free, 0/5
    mock_cosmos._execute_operation.return_value = make_usage("limituser", presentationsCreated=5, tier="free")
    allowed, reason = await svc.can_create_presentation("limituser")
    assert allowed is False
    assert "limit" in reason
    # Upgrade to educator, should be unlimited
    mock_cosmos._execute_operation.return_value = make_usage("limituser", presentationsCreated=123, tier="educator")
    allowed, reason = await svc.can_create_presentation("limituser")
    assert allowed is True
    # Downgrade back to free, over the limit persists
    mock_cosmos._execute_operation.return_value = make_usage("limituser", presentationsCreated=6, tier="free")
    allowed, reason = await svc.can_create_presentation("limituser")
    assert allowed is False
    # Upgrade to pro should be unlimited
    mock_cosmos._execute_operation.return_value = make_usage("limituser", presentationsCreated=9999, tier="pro")
    allowed, reason = await svc.can_create_presentation("limituser")
    assert allowed is True
    # Set to free, under limit works
    mock_cosmos._execute_operation.return_value = make_usage("limituser", presentationsCreated=2, tier="free")
    allowed, reason = await svc.can_create_presentation("limituser")
    assert allowed is True

@pytest.mark.asyncio
async def test_e2e_tier_export_limits_behavior():
    mock_cosmos = MagicMock()
    svc = UsageService(mock_cosmos)
    mock_cosmos._execute_operation = AsyncMock()
    # Free cannot export
    mock_cosmos._execute_operation.return_value = make_usage("exportu", tier="free")
    allowed, reason = await svc.can_export("exportu")
    assert allowed is False
    assert "Export is available" in reason
    # Educator can export
    mock_cosmos._execute_operation.return_value = make_usage("exportu", tier="educator")
    allowed, reason = await svc.can_export("exportu")
    assert allowed is True
    # Pro can export
    mock_cosmos._execute_operation.return_value = make_usage("exportu", tier="pro")
    allowed, reason = await svc.can_export("exportu")
    assert allowed is True
