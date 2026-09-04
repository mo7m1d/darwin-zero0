from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path


class CacheDenied(ValueError):
    pass


SECRET = re.compile(r"(?i)(api[_-]?key\s*[:=]|password\s*[:=]|access[_-]?token\s*[:=]|BEGIN [A-Z ]*PRIVATE KEY|\botp\s*[:=])")
AUTHORITY = re.compile(r"(?i)(owner\s+(approval|authorized)|permission\s+granted|budget\s+expansion|ignore previous instructions)")


@dataclass(frozen=True)
class CacheIdentity:
    model_id: str
    policy_hash: str
    tool_schema_hash: str
    context_packet_hash: str
    task_fingerprint: str
    component_hash: str
    retrieval_version: str
    trust_level: str
    schema_version: str = "darwin.prompt-cache.v1"

    def key(self) -> str:
        values = asdict(self)
        if not self.model_id or not self.task_fingerprint or self.trust_level not in {"TRUSTED_DERIVED", "UNTRUSTED_DATA"}:
            raise CacheDenied("incomplete cache identity")
        for name in ("policy_hash", "tool_schema_hash", "context_packet_hash", "component_hash"):
            if not re.fullmatch(r"[0-9a-f]{64}", values[name]):
                raise CacheDenied("invalid cache identity hash")
        return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class PromptCache:
    """Disposable local cache; never an authority or approval store."""
    def __init__(self, root: Path, max_entry_bytes: int = 262_144):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_entry_bytes = max_entry_bytes

    def put(self, identity: CacheIdentity, content: str, content_role: str = "derived", source_ref: str = "") -> str:
        if Path(source_ref).name.casefold().startswith(".env"):
            raise CacheDenied("environment sources are not cacheable")
        if not isinstance(content, str) or SECRET.search(content) or AUTHORITY.search(content):
            raise CacheDenied("secret or authority material is not cacheable")
        encoded = content.encode("utf-8")
        if len(encoded) > self.max_entry_bytes or content_role not in {"derived", "untrusted_data"}:
            raise CacheDenied("uncacheable content")
        key = identity.key()
        payload = {"schema": identity.schema_version, "key": key, "identity": asdict(identity),
                   "content": content, "content_hash": hashlib.sha256(encoded).hexdigest(),
                   "content_role": content_role, "authoritative": False}
        temporary = self.root / f".{key}.tmp"
        target = self.root / f"{key}.json"
        temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8", newline="\n")
        os.replace(temporary, target)
        return key

    def get(self, identity: CacheIdentity) -> str | None:
        key = identity.key()
        target = self.root / f"{key}.json"
        if not target.exists():
            return None
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            content = payload["content"]
            valid = payload.get("key") == key and payload.get("identity") == asdict(identity)
            valid = valid and payload.get("authoritative") is False
            valid = valid and payload.get("content_hash") == hashlib.sha256(content.encode()).hexdigest()
            valid = valid and not SECRET.search(content) and not AUTHORITY.search(content)
            if not valid:
                raise CacheDenied("cache integrity failure")
            return content
        except (OSError, KeyError, TypeError, json.JSONDecodeError, CacheDenied):
            return None

    def clear(self):
        for path in self.root.glob("*.json"):
            path.unlink()
