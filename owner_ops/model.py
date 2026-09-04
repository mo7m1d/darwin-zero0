from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

ALLOWED_ACTIONS = frozenset({
    "STATUS", "REFRESH", "PAUSE", "RESUME", "FREEZE",
    "TASK_DETAILS", "BUDGET_DETAILS", "RECOVERY_DETAILS", "MODEL_DETAILS",
    "DECISION_DETAILS", "APPROVE", "DENY",
})
ALERT_LEVELS = frozenset({"INFO", "WARNING", "OWNER_DECISION", "CRITICAL"})

@dataclass(frozen=True)
class OwnerEvent:
    event_id: str
    kind: str
    payload: dict[str, Any]
    created_at: int
    severity: str = "INFO"

    def validate(self) -> "OwnerEvent":
        if not self.event_id or len(self.event_id) > 128:
            raise ValueError("invalid event id")
        if not self.kind or len(self.kind) > 128:
            raise ValueError("invalid event kind")
        if self.severity not in ALERT_LEVELS:
            raise ValueError("invalid severity")
        if isinstance(self.created_at, bool) or not isinstance(self.created_at, int) or self.created_at < 0:
            raise ValueError("invalid event timestamp")
        if not isinstance(self.payload, dict):
            raise ValueError("invalid event payload")
        import json
        if len(json.dumps(self.payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")) > 65536:
            raise ValueError("event payload too large")
        return self

@dataclass(frozen=True)
class ControlRequest:
    action: str
    request_id: str
    owner_user_id: str
    guild_id: str
    channel_id: str
    nonce: str
    expires_at: int
    target_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> "ControlRequest":
        if self.action not in ALLOWED_ACTIONS:
            raise ValueError("unsupported control action")
        for name, value, limit in (
            ("request_id", self.request_id, 128), ("owner_user_id", self.owner_user_id, 128),
            ("guild_id", self.guild_id, 128), ("channel_id", self.channel_id, 128),
            ("nonce", self.nonce, 256), ("target_id", self.target_id, 256),
        ):
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError(f"invalid {name}")
        if not all((self.request_id, self.owner_user_id, self.guild_id, self.channel_id, self.nonce)):
            raise ValueError("missing control identity")
        if isinstance(self.expires_at, bool) or not isinstance(self.expires_at, int) or self.expires_at < 0:
            raise ValueError("invalid expiry")
        if not isinstance(self.payload, dict):
            raise ValueError("invalid payload")
        return self
