from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path


class RegistryError(ValueError):
    pass


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_hash(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def integer(value, label: str, maximum: int = 2**63 - 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > maximum:
        raise RegistryError(f"invalid {label}")
    return value


@dataclass(frozen=True)
class ModelRecord:
    model_id: str
    provider_id: str
    upstream_model: str
    aliases: tuple[str, ...] = ()
    enabled: bool = True
    location: str = "remote"
    price_class: str = "unknown"
    input_micros_per_million: int | None = None
    output_micros_per_million: int | None = None
    cache_read_micros_per_million: int | None = None
    cache_write_micros_per_million: int | None = None
    pricing_source: str = ""
    pricing_version: str = ""
    pricing_effective_at: str = ""
    context_limit: int = 0
    output_limit: int = 0
    capabilities: frozenset[str] = field(default_factory=frozenset)
    coding_class: int = 0
    latency_class: int = 0
    privacy_class: str = "remote-standard"
    health: str = "healthy"
    reliability: int = 0
    evaluation_version: str = ""
    owner_approved: bool = False
    status: str = "CANDIDATE"

    def validate(self) -> "ModelRecord":
        for name, value in (("model_id", self.model_id), ("provider_id", self.provider_id),
                            ("upstream_model", self.upstream_model)):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{1,127}", value):
                raise RegistryError(f"invalid {name}")
        if re.search(r"(?:^|[-_/:])(latest|auto)(?:$|[-_/:])", self.upstream_model, re.IGNORECASE):
            raise RegistryError("mutable upstream model identity")
        if self.location not in {"local", "remote"} or self.price_class not in {"free", "paid", "unknown"}:
            raise RegistryError("invalid model classification")
        rates = (self.input_micros_per_million, self.output_micros_per_million,
                 self.cache_read_micros_per_million, self.cache_write_micros_per_million)
        if self.price_class == "unknown":
            if any(rate is not None for rate in rates):
                raise RegistryError("unknown pricing cannot carry trusted rates")
        else:
            if any(rate is None for rate in rates):
                raise RegistryError("known pricing requires all rates")
            for rate in rates:
                integer(rate, "price")
            if self.price_class == "free" and any(rates):
                raise RegistryError("free model has nonzero price")
            if self.price_class == "paid" and not any(rates):
                raise RegistryError("paid model has zero price")
            if not self.pricing_source or not self.pricing_version or not self.pricing_effective_at:
                raise RegistryError("pricing provenance required")
        integer(self.context_limit, "context_limit")
        integer(self.output_limit, "output_limit")
        integer(self.coding_class, "coding_class", 100)
        integer(self.latency_class, "latency_class", 100)
        integer(self.reliability, "reliability", 100)
        if self.status not in {"CANDIDATE", "ACCEPTED", "REJECTED", "QUARANTINED"}:
            raise RegistryError("invalid status")
        if self.status == "ACCEPTED" and (not self.owner_approved or not self.evaluation_version):
            raise RegistryError("accepted model lacks approval/evaluation")
        return self

    @property
    def known_zero_cost(self) -> bool:
        return self.price_class == "free" and all(rate == 0 for rate in (
            self.input_micros_per_million, self.output_micros_per_million,
            self.cache_read_micros_per_million, self.cache_write_micros_per_million))

    def dictionary(self) -> dict:
        value = asdict(self)
        value["aliases"] = list(self.aliases)
        value["capabilities"] = sorted(self.capabilities)
        return value


class ModelRegistry:
    def __init__(self, records: list[ModelRecord]):
        self._records: dict[str, ModelRecord] = {}
        self._aliases: dict[str, str] = {}
        for record in records:
            record.validate()
            if record.model_id in self._records:
                raise RegistryError("duplicate model_id")
            self._records[record.model_id] = record
            for alias in record.aliases:
                folded = alias.casefold()
                if folded in self._aliases or folded in {key.casefold() for key in self._records}:
                    raise RegistryError("ambiguous alias")
                self._aliases[folded] = record.model_id
        self.registry_hash = content_hash([record.dictionary() for record in sorted(records, key=lambda item: item.model_id)])

    def resolve(self, identity: str) -> ModelRecord:
        model_id = identity if identity in self._records else self._aliases.get(identity.casefold())
        if not model_id:
            raise RegistryError("unknown model identity")
        return self._records[model_id]

    def accepted(self) -> list[ModelRecord]:
        return [record for record in self._records.values()
                if record.enabled and record.owner_approved and record.status == "ACCEPTED"]

    def write(self, path: Path) -> None:
        payload = {"schema": "darwin.model-registry.v1", "registry_hash": self.registry_hash,
                   "models": [record.dictionary() for record in sorted(self._records.values(), key=lambda item: item.model_id)]}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
