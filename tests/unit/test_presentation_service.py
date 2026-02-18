import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
import uuid

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent / 'src'))

from services.presentation_service import PresentationService

class DummyCosmos:
    def __init__(self):
        self.created = None
        self.replaced = None
        self.deleted = None
        self.read_val = None
        self.queried = None
        self._container = MagicMock()
        self._container.create_item = AsyncMock(side_effect=self._fake_create)
        self._container.replace_item = AsyncMock(side_effect=self._fake_replace)
        self._container.delete_item = AsyncMock(side_effect=self._fake_delete)
        self._container.read_item = AsyncMock(side_effect=self._fake_read)

    def get_container_client(self, name):
        return self._container

    async def _execute_operation(self, op_name, func, *args, **kwargs):
        return await func(*args, **kwargs)

    async def query_items(self, container, query, params, partition_key=None):
        return self.queried

    async def _fake_create(self, **kwargs):
        self.created = kwargs["body"]
        return self.created

    async def _fake_replace(self, **kwargs):
        self.replaced = kwargs["body"]
        return self.replaced

    async def _fake_delete(self, **kwargs):
        self.deleted = kwargs
        return {}

    async def _fake_read(self, **kwargs):
        return self.read_val

@pytest.mark.asyncio
async def test_create():
    cosmos = DummyCosmos()
    service = PresentationService(cosmos)
    slides = [{"title": "Title", "content": "Content"}]
    result = await service.create("uid1", "Test Pres", slides, "Transcript")
    assert result["userId"] == "uid1"
    assert result["title"] == "Test Pres"
    assert result["slides"] == slides
    assert result["slideCount"] == 1
    assert "createdAt" in result
    assert "updatedAt" in result
    created_doc = cosmos.created
    assert created_doc == result

@pytest.mark.asyncio
async def test_get():
    cosmos = DummyCosmos()
    cosmos.read_val = {"id": "pres-1", "userId": "uid1"}
    service = PresentationService(cosmos)
    res = await service.get("uid1", "pres-1")
    assert res["id"] == "pres-1"
    assert res["userId"] == "uid1"

@pytest.mark.asyncio
async def test_list():
    cosmos = DummyCosmos()
    cosmos.queried = [
        {"id": "pres-1", "title": "A", "slideCount": 2, "createdAt": "t1", "updatedAt": "t2"}
    ]
    service = PresentationService(cosmos)
    res = await service.list_for_user("uid1")
    assert isinstance(res, list)
    assert res[0]["id"] == "pres-1"

@pytest.mark.asyncio
async def test_update():
    cosmos = DummyCosmos()
    old_doc = {"id": "pres-1", "userId": "uid1", "title": "old", "slides": [1], "slideCount": 1, "updatedAt": "zzz"}
    cosmos.read_val = old_doc.copy()
    service = PresentationService(cosmos)
    new_slides = [1,2,3]
    updates = {"title": "new-title", "slides": new_slides}
    res = await service.update("uid1", "pres-1", updates)
    assert res["title"] == "new-title"
    assert res["slides"] == new_slides
    assert res["slideCount"] == len(new_slides)
    assert res["updatedAt"] != "zzz"
    replaced = cosmos.replaced
    assert replaced == res

@pytest.mark.asyncio
async def test_delete():
    cosmos = DummyCosmos()
    service = PresentationService(cosmos)
    ok = await service.delete("uid2", "pres-del")
    assert ok
    assert cosmos.deleted["item"] == "pres-del"
    assert cosmos.deleted["partition_key"] == "uid2"

@pytest.mark.asyncio
async def test_delete_not_found():
    cosmos = DummyCosmos()
    cosmos._container.delete_item = AsyncMock(side_effect=Exception("not found"))
    service = PresentationService(cosmos)
    ok = await service.delete("uidX", "pres404")
    assert ok is False
