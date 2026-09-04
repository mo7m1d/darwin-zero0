from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class PlatformDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class PlatformAction:
    platform_id: str
    action: str
    dry_run: bool = True
    owner_authorized: bool = False
    external_effect: bool = False
    capital_required_cents: int = 0
    owner_approval_ref: str = ""
    owner_approval_hash: str = ""


class PlatformRegistry:
    def __init__(self, path: Path | None = None):
        path = path or Path(__file__).with_name("platform_registry.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.schema = payload["schema"]
        self._platforms = {item["platform_id"]: item for item in payload["platforms"]}

    def get(self, platform_id: str) -> dict:
        if platform_id not in self._platforms:
            raise PlatformDenied("unregistered platform")
        return dict(self._platforms[platform_id])

    def records(self) -> list[dict]:
        return [dict(self._platforms[key]) for key in sorted(self._platforms)]


class PlatformAdapter:
    """Contract only. ECO00 contains no live marketplace writer."""

    def __init__(self, registry: PlatformRegistry):
        self.registry = registry

    def authorize(self, request: PlatformAction) -> dict:
        record = self.registry.get(request.platform_id)
        if record["default_mode"] != "DRY_RUN":
            raise PlatformDenied("unsafe platform default")
        if record["status"] == "ACCESS_REVIEW_REQUIRED":
            raise PlatformDenied("platform access review required")
        if request.platform_id == "ebay" and request.action == "retail_marketplace_direct_fulfillment":
            raise PlatformDenied("prohibited eBay fulfillment model")
        owner_verified = (request.owner_authorized is True and bool(request.owner_approval_ref)
                          and len(request.owner_approval_hash) == 64
                          and all(char in "0123456789abcdef" for char in request.owner_approval_hash))
        if request.external_effect and (request.dry_run or not owner_verified):
            raise PlatformDenied("external effect requires explicit Owner authorization outside dry run")
        if request.capital_required_cents > 0 and not owner_verified:
            raise PlatformDenied("capital requires explicit Owner authorization")
        return {"platform_id": request.platform_id, "action": request.action,
                "mode": "DRY_RUN" if request.dry_run else "OWNER_AUTHORIZED_EXECUTION",
                "api_availability_is_permission": False}
