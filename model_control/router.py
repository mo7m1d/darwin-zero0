from __future__ import annotations

from dataclasses import dataclass

from .registry import ModelRecord, ModelRegistry


class RoutingDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class RouteRequirements:
    task_class: str
    capabilities: frozenset[str]
    risk_class: str = "LOW"
    context_tokens: int = 0
    output_tokens: int = 0
    min_coding_class: int = 0
    privacy_allowed: frozenset[str] = frozenset({"local", "remote-standard"})
    max_latency_class: int = 100
    spend_authorized: bool = False
    spend_remaining_micros: int = 0
    accepted_pricing_versions: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RouteDecision:
    model_id: str
    provider_id: str
    upstream_model: str
    estimated_max_micros: int
    rationale: tuple[str, ...]


def charge(tokens: int, micros_per_million: int) -> int:
    if tokens < 0 or micros_per_million < 0:
        raise RoutingDenied("invalid cost input")
    return (tokens * micros_per_million + 999_999) // 1_000_000


class Router:
    def __init__(self, registry: ModelRegistry):
        self.registry = registry

    def maximum_cost(self, model: ModelRecord, requirements: RouteRequirements) -> int:
        if model.price_class == "unknown":
            raise RoutingDenied("UNKNOWN_PRICING")
        return charge(requirements.context_tokens, model.input_micros_per_million or 0) + charge(
            requirements.output_tokens, model.output_micros_per_million or 0)

    def _qualifies(self, model: ModelRecord, req: RouteRequirements) -> tuple[bool, str, int]:
        if not req.capabilities.issubset(model.capabilities):
            return False, "capability", 0
        if req.context_tokens > model.context_limit or req.output_tokens > model.output_limit:
            return False, "capacity", 0
        if model.coding_class < req.min_coding_class or model.latency_class > req.max_latency_class:
            return False, "quality_or_latency", 0
        if model.privacy_class not in req.privacy_allowed:
            return False, "privacy", 0
        if model.health != "healthy":
            return False, "health", 0
        if model.price_class == "unknown":
            return False, "unknown_price", 0
        if req.accepted_pricing_versions and model.pricing_version not in req.accepted_pricing_versions:
            return False, "stale_pricing", 0
        cost = self.maximum_cost(model, req)
        if cost and (not req.spend_authorized or cost > req.spend_remaining_micros):
            return False, "OWNER_DECISION", cost
        return True, "qualified", cost

    def route(self, requirements: RouteRequirements, exclude: frozenset[str] = frozenset()) -> RouteDecision:
        if requirements.context_tokens < 0 or requirements.output_tokens < 0 or requirements.spend_remaining_micros < 0:
            raise RoutingDenied("invalid requirements")
        qualified: list[tuple[ModelRecord, int]] = []
        reasons: set[str] = set()
        for model in self.registry.accepted():
            if model.model_id in exclude:
                continue
            ok, reason, cost = self._qualifies(model, requirements)
            reasons.add(reason)
            if ok:
                qualified.append((model, cost))
        if not qualified:
            raise RoutingDenied("OWNER_DECISION" if "OWNER_DECISION" in reasons else "NO_QUALIFYING_MODEL")
        model, cost = min(qualified, key=lambda item: (
            0 if item[0].known_zero_cost else 1,
            item[1], -item[0].reliability, -item[0].coding_class,
            item[0].latency_class, item[0].model_id))
        return RouteDecision(model.model_id, model.provider_id, model.upstream_model, cost,
                             ("required_capabilities_satisfied", "owner_policy_satisfied",
                              "known_zero_cost" if cost == 0 else "owner_authorized_paid",
                              f"registry={self.registry.registry_hash}"))

    def fallback(self, failed: RouteDecision, requirements: RouteRequirements) -> RouteDecision:
        decision = self.route(requirements, frozenset({failed.model_id}))
        if failed.estimated_max_micros == 0 and decision.estimated_max_micros > 0 and not requirements.spend_authorized:
            raise RoutingDenied("SILENT_PAID_FALLBACK_BLOCKED")
        return decision
