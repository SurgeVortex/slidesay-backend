import uuid
from datetime import datetime, timezone
from typing import Optional

from src.database.cosmos_service import CosmosService

class PresentationService:
    CONTAINER = "presentations"

    def __init__(self, cosmos: CosmosService):
        self.cosmos = cosmos

    async def create(self, user_id: str, title: str, slides: list, transcript: str = "") -> dict:
        doc = {
            "id": str(uuid.uuid4()),
            "userId": user_id,
            "title": title,
            "slides": slides,
            "transcript": transcript,
            "slideCount": len(slides),
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        container = self.cosmos.get_container_client(self.CONTAINER)
        await self.cosmos._execute_operation(
            "create_presentation", container.create_item, body=doc
        )
        return doc

    async def get(self, user_id: str, presentation_id: str) -> Optional[dict]:
        container = self.cosmos.get_container_client(self.CONTAINER)
        # id and partition key are presentation_id and user_id respectively
        result = await self.cosmos._execute_operation(
            "get_presentation",
            container.read_item,
            item=presentation_id,
            partition_key=user_id,
        )
        return result if isinstance(result, dict) else None

    async def list_for_user(self, user_id: str, limit: int = 50, offset: int = 0) -> list:
        query = (
            "SELECT c.id, c.title, c.slideCount, c.createdAt, c.updatedAt "
            "FROM c WHERE c.userId = @userId "
            "ORDER BY c.updatedAt DESC OFFSET @offset LIMIT @limit"
        )
        params = [
            {"name": "@userId", "value": user_id},
            {"name": "@offset", "value": offset},
            {"name": "@limit", "value": limit},
        ]
        return await self.cosmos.query_items(self.CONTAINER, query, params, partition_key=user_id)

    async def update(self, user_id: str, presentation_id: str, updates: dict) -> Optional[dict]:
        container = self.cosmos.get_container_client(self.CONTAINER)
        existing = await self.get(user_id, presentation_id)
        if not existing:
            return None
        for key in ["title", "slides"]:
            if key in updates:
                existing[key] = updates[key]
        if "slides" in updates:
            existing["slideCount"] = len(updates["slides"])
        existing["updatedAt"] = datetime.now(timezone.utc).isoformat()
        await self.cosmos._execute_operation(
            "update_presentation",
            container.replace_item,
            item=presentation_id,
            body=existing,
        )
        return existing

    async def delete(self, user_id: str, presentation_id: str) -> bool:
        container = self.cosmos.get_container_client(self.CONTAINER)
        try:
            await self.cosmos._execute_operation(
                "delete_presentation",
                container.delete_item,
                item=presentation_id,
                partition_key=user_id,
            )
            return True
        except Exception:
            return False
