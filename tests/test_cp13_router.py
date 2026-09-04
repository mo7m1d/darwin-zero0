import json
from pathlib import Path

import pytest

from model_control import ModelRecord, ModelRegistry, RegistryError, RouteRequirements, Router, RoutingDenied
from tests.cp13_helpers import models


def req(capabilities, **kwargs):
    values = {"context_tokens": 1000, "output_tokens": 100,
              "privacy_allowed": frozenset({"local", "remote-standard"})}
    values.update(kwargs)
    return RouteRequirements("fixture", frozenset(capabilities), **values)


def test_prefers_capable_known_zero_cost():
    assert Router(models()).route(req({"coding", "tools"})).model_id == "local.code.v1"


def test_not_cheapest_when_capability_missing():
    with pytest.raises(RoutingDenied, match="OWNER_DECISION"):
        Router(models()).route(req({"reasoning"}))


def test_paid_requires_owner_and_budget():
    router = Router(models())
    assert router.route(req({"reasoning"}, spend_authorized=True, spend_remaining_micros=10_000)).model_id == "remote.paid.v1"
    with pytest.raises(RoutingDenied):
        router.route(req({"reasoning"}, spend_authorized=True, spend_remaining_micros=1))


def test_unknown_price_is_not_free():
    registry = models()
    assert not registry.resolve("unknown.v1").known_zero_cost


def test_alias_is_fixed_to_identity():
    registry = models()
    assert registry.resolve("safe-local").model_id == "local.code.v1"
    with pytest.raises(RegistryError):
        registry.resolve("latest")


def test_mutable_upstream_rejected():
    with pytest.raises(RegistryError):
        ModelRegistry([ModelRecord("bad.model", "p", "vendor/latest", price_class="unknown")])


def test_free_label_with_nonzero_rate_rejected():
    with pytest.raises(RegistryError):
        ModelRecord("bad.free", "p", "p/model-1", price_class="free",
                    input_micros_per_million=1, output_micros_per_million=0,
                    cache_read_micros_per_million=0, cache_write_micros_per_million=0,
                    pricing_source="x", pricing_version="1", pricing_effective_at="now").validate()


def test_context_output_and_tool_limits_enforced():
    router = Router(models())
    with pytest.raises(RoutingDenied):
        router.route(req({"coding"}, context_tokens=200_000))
    with pytest.raises(RoutingDenied):
        router.route(req({"coding"}, output_tokens=30_000))


def test_privacy_boundary_enforced():
    decision = Router(models()).route(req({"coding"}, privacy_allowed=frozenset({"local"})))
    assert decision.provider_id == "local"


def test_fallback_revalidates_and_never_silently_pays():
    router = Router(models())
    first = router.route(req({"coding", "tools"}))
    with pytest.raises(RoutingDenied):
        router.fallback(first, req({"coding", "tools"}))


def test_registry_is_deterministically_hashed(tmp_path):
    one = models()
    two = models()
    assert one.registry_hash == two.registry_hash
    one.write(tmp_path / "registry.json")
    assert json.loads((tmp_path / "registry.json").read_text())["registry_hash"] == one.registry_hash


@pytest.mark.parametrize("case", json.loads((Path(__file__).parent / "fixtures/cp13/router_holdout.json").read_text())["cases"], ids=lambda item: item["name"])
def test_router_holdout(case):
    requirements = RouteRequirements(
        "holdout", frozenset(case["capabilities"]),
        context_tokens=case.get("context_tokens", 1000), output_tokens=100,
        privacy_allowed=frozenset(case["privacy"]),
        spend_authorized=case.get("spend_authorized", False),
        spend_remaining_micros=case.get("spend_remaining_micros", 0),
    )
    try:
        actual = Router(models()).route(requirements).model_id
    except RoutingDenied as error:
        actual = str(error)
    assert actual == case["expected"]
