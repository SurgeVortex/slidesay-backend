from typing import Optional, Any
from src.database.cosmos_service import CosmosService

class UserService:
    def __init__(self, cosmos_service: Optional[CosmosService] = None):
        self.cosmos_service = cosmos_service or CosmosService()

    async def create_user(self, user_data: dict[str, Any]) -> dict[str, Any] | None:
        return await self.cosmos_service.create_user(user_data)

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        return await self.cosmos_service.get_user_by_id(user_id)

    async def update_user(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        return await self.cosmos_service.update_user(user_id, updates)

    async def delete_user(self, user_id: str) -> bool:
        # In CosmosService: delete_user is a soft delete
        return await self.cosmos_service.delete_user(user_id)

    async def ensure_profile(self, user_id: str, user_info: dict[str, Any]) -> dict[str, Any]:
        """Auto-create user profile if not found, or return existing profile."""
        user = await self.get_user(user_id)
        if user:
            return user
        # Compose minimal user profile data
        user_data = {"id": user_id, "userId": user_id}
        user_data.update(user_info)
        return await self.create_user(user_data)
