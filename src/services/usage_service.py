from datetime import UTC, datetime


class UsageService:
    CONTAINER = "usage"

    TIER_LIMITS = {
        "free": {"presentations": 5, "exports": 0},
        "educator": {"presentations": -1, "exports": -1},  # -1 = unlimited
        "pro": {"presentations": -1, "exports": -1},
    }

    def __init__(self, cosmos):
        self.cosmos = cosmos

    async def get_usage(self, user_id: str) -> dict:
        """Get current month's usage for a user."""
        month_key = datetime.now(UTC).strftime("%Y-%m")
        doc_id = f"{user_id}:{month_key}"
        try:
            # CosmosService doesn't have strict read_item, so assume similar API
            usage = await self.cosmos._execute_operation(
                "get_usage",
                self.cosmos.get_container_client(self.CONTAINER).read_item,
                item=doc_id,
                partition_key=user_id,
            )
            if not usage:
                raise Exception("Not found")
            return usage
        except Exception:
            return {
                "id": doc_id,
                "userId": user_id,
                "month": month_key,
                "presentationsCreated": 0,
                "exportsUsed": 0,
                "tier": "free",
            }

    async def can_create_presentation(self, user_id: str) -> tuple[bool, str]:
        usage = await self.get_usage(user_id)
        tier = usage.get("tier", "free")
        limit = self.TIER_LIMITS.get(tier, self.TIER_LIMITS["free"])["presentations"]
        if limit == -1:
            return True, "ok"
        if usage["presentationsCreated"] >= limit:
            return False, f"Monthly limit of {limit} presentations reached. Upgrade to create more."
        return True, "ok"

    async def can_export(self, user_id: str) -> tuple[bool, str]:
        usage = await self.get_usage(user_id)
        tier = usage.get("tier", "free")
        limit = self.TIER_LIMITS.get(tier, self.TIER_LIMITS["free"])["exports"]
        if limit == -1:
            return True, "ok"
        if limit == 0:
            return False, "Export is available on Educator ($5/mo) and Pro ($9/mo) plans."
        if usage["exportsUsed"] >= limit:
            return False, f"Monthly export limit of {limit} reached."
        return True, "ok"

    async def record_presentation_created(self, user_id: str) -> dict:
        usage = await self.get_usage(user_id)
        usage["presentationsCreated"] += 1
        await self.cosmos._execute_operation(
            "record_presentation_created",
            self.cosmos.get_container_client(self.CONTAINER).upsert_item,
            body=usage
        )
        return usage

    async def record_export(self, user_id: str) -> dict:
        usage = await self.get_usage(user_id)
        usage["exportsUsed"] += 1
        await self.cosmos._execute_operation(
            "record_export",
            self.cosmos.get_container_client(self.CONTAINER).upsert_item,
            body=usage
        )
        return usage

    async def set_tier(self, user_id: str, tier: str) -> dict:
        if tier not in self.TIER_LIMITS:
            raise ValueError(f"Invalid tier: {tier}")
        usage = await self.get_usage(user_id)
        usage["tier"] = tier
        await self.cosmos._execute_operation(
            "set_tier",
            self.cosmos.get_container_client(self.CONTAINER).upsert_item,
            body=usage
        )
        return usage
