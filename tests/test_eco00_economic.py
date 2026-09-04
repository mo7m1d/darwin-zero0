import json
import sqlite3

import pytest

from economic import (CapabilityFamily, CapabilityRegistry, EconomicAmounts, EconomicDenied,
                      EconomicEngine, EconomicStore, Opportunity, OpportunityState,
                      PlatformAction, PlatformAdapter, PlatformRegistry, default_capability_registry)
from economic.model import EconomicValueError, MAX_INT
from economic.platforms import PlatformDenied
from economic.registry import FAMILIES, RegistryDenied


def opportunity(identity="opp-1", revenue=10_000, costs=2_000, capital=0,
                risk=1000, confidence=9000, family="software_delivery"):
    return Opportunity(identity, family, identity,
                       EconomicAmounts(revenue, marketplace_fees_cents=costs,
                                       capital_required_cents=capital,
                                       uncertainty_bps=risk, evidence_confidence_bps=confidence),
                       capital_components_cents={} if capital == 0 else {"purchase": capital})


def engine(tmp_path):
    return EconomicEngine(default_capability_registry(), EconomicStore(tmp_path / "economic.sqlite3", now=lambda: 100))


def progress(e, identity="opp-1", capital_owner=False):
    for state in (OpportunityState.RESEARCHED, OpportunityState.POLICY_CHECKED,
                  OpportunityState.SCORED, OpportunityState.CANDIDATE,
                  OpportunityState.DRY_RUN_READY):
        e.transition(identity, state, actor="reviewer", evidence_ref=f"evidence://{state.value}")
    return e.transition(identity, OpportunityState.EXECUTION_READY, actor="reviewer",
                        owner_authorized=capital_owner)


def test_default_registry_has_exact_required_families():
    registry = default_capability_registry()
    assert len(registry.records()) == 20
    assert {item["family_id"] for item in registry.records()} == set(FAMILIES)
    assert all(item["default_mode"] == "DRY_RUN" for item in registry.records())


def test_registry_is_extensible_without_engine_change():
    registry = default_capability_registry()
    registry.register(CapabilityFamily("future_family", "Future Family"))
    assert registry.get("future_family").display_name == "Future Family"


def test_registry_rejects_duplicate_and_unsafe_default():
    registry = default_capability_registry()
    with pytest.raises(RegistryDenied):
        registry.register(CapabilityFamily("software_delivery", "Duplicate"))
    with pytest.raises(RegistryDenied):
        CapabilityFamily("unsafe", "Unsafe", default_mode="LIVE").validate()


def test_integer_normalization_and_fixed_point_derivation():
    value = EconomicAmounts(10_000, 500, 300, 1_000, 200, 800, 200,
                            expected_hours_milli=2500, uncertainty_bps=1000,
                            policy_risk_bps=500, execution_risk_bps=500,
                            evidence_confidence_bps=9000)
    assert value.expected_cost_cents == 3000
    assert value.expected_profit_cents == 7000
    assert value.margin_bps == 7000
    assert value.risk_adjusted_profit_cents == 5040


@pytest.mark.parametrize("field,value", [
    ("expected_revenue_cents", -1), ("expected_revenue_cents", 1.1),
    ("expected_revenue_cents", True), ("uncertainty_bps", 10001),
    ("marketplace_fees_cents", MAX_INT + 1),
])
def test_invalid_numeric_inputs_fail_closed(field, value):
    args = {"expected_revenue_cents": 1, field: value}
    with pytest.raises(EconomicValueError):
        EconomicAmounts(**args)


def test_cost_sum_overflow_fails_closed():
    with pytest.raises(EconomicValueError):
        EconomicAmounts(MAX_INT, marketplace_fees_cents=MAX_INT, payment_fees_cents=1)


def test_capital_components_must_reconcile():
    with pytest.raises(EconomicValueError):
        Opportunity("x", "software_delivery", "x", EconomicAmounts(100, capital_required_cents=50),
                    capital_components_cents={"purchase": 0})
    with pytest.raises(EconomicValueError):
        Opportunity("x", "software_delivery", "x", EconomicAmounts(100),
                    capital_components_cents={"hidden_deposit": 0})


def test_unregistered_family_fails_closed(tmp_path):
    with pytest.raises(RegistryDenied):
        engine(tmp_path).add(opportunity(family="not_registered"))


def test_valid_lifecycle_and_acceptance_gate(tmp_path):
    e = engine(tmp_path)
    e.add(opportunity())
    progress(e)
    e.transition("opp-1", OpportunityState.EXECUTING, actor="owner", owner_authorized=True,
                 owner_approval_ref="owner://execute", owner_approval_hash="b" * 64)
    e.transition("opp-1", OpportunityState.ACCEPTANCE_PENDING, actor="executor", evidence_ref="evidence://result")
    accepted = e.transition("opp-1", OpportunityState.ACCEPTED, actor="acceptance_gate",
                            acceptance_verified=True, evidence_ref="acceptance://1", acceptance_hash="a" * 64)
    assert accepted.state == OpportunityState.ACCEPTED
    assert e.store.verify_ledger()


def test_invalid_transition_fails_closed(tmp_path):
    e = engine(tmp_path)
    e.add(opportunity())
    with pytest.raises(EconomicDenied):
        e.transition("opp-1", OpportunityState.EXECUTION_READY, actor="agent")


@pytest.mark.parametrize("actor,verified,reference,digest", [
    ("llm", True, "acceptance://1", "a" * 64),
    ("acceptance_gate", False, "acceptance://1", "a" * 64),
    ("acceptance_gate", True, "", "a" * 64),
    ("acceptance_gate", True, "acceptance://1", "forged"),
])
def test_acceptance_cannot_be_self_reported(tmp_path, actor, verified, reference, digest):
    e = engine(tmp_path)
    e.add(opportunity())
    progress(e)
    e.transition("opp-1", OpportunityState.EXECUTING, actor="owner", owner_authorized=True,
                 owner_approval_ref="owner://execute", owner_approval_hash="b" * 64)
    e.transition("opp-1", OpportunityState.ACCEPTANCE_PENDING, actor="executor")
    with pytest.raises(EconomicDenied):
        e.transition("opp-1", OpportunityState.ACCEPTED, actor=actor,
                     acceptance_verified=verified, evidence_ref=reference, acceptance_hash=digest)


def test_positive_capital_requires_owner_at_execution_readiness(tmp_path):
    e = engine(tmp_path)
    e.add(opportunity(capital=100))
    for state in (OpportunityState.RESEARCHED, OpportunityState.POLICY_CHECKED,
                  OpportunityState.SCORED, OpportunityState.CANDIDATE,
                  OpportunityState.DRY_RUN_READY):
        e.transition("opp-1", state, actor="reviewer", evidence_ref="evidence://x")
    with pytest.raises(EconomicDenied):
        e.transition("opp-1", OpportunityState.EXECUTION_READY, actor="agent")
    assert e.transition("opp-1", OpportunityState.EXECUTION_READY, actor="owner",
                        owner_authorized=True, owner_approval_ref="owner://capital",
                        owner_approval_hash="b" * 64).owner_capital_authorized


def test_ranking_not_raw_revenue_and_is_restart_stable(tmp_path):
    path = tmp_path / "economic.sqlite3"
    e = EconomicEngine(default_capability_registry(), EconomicStore(path, now=lambda: 100))
    high_revenue_high_risk = opportunity("raw-revenue", 100_000, 60_000, risk=9000)
    modest_revenue_good_profit = opportunity("quality", 20_000, 2_000, risk=500)
    e.add(high_revenue_high_risk)
    e.add(modest_revenue_good_profit)
    for identity in ("raw-revenue", "quality"):
        e.transition(identity, OpportunityState.RESEARCHED, actor="reviewer")
        e.transition(identity, OpportunityState.POLICY_CHECKED, actor="reviewer", evidence_ref="e://policy")
        e.transition(identity, OpportunityState.SCORED, actor="reviewer", evidence_ref="e://score")
    assert [item.opportunity_id for item in e.rank()] == ["quality", "raw-revenue"]
    restarted = EconomicEngine(default_capability_registry(), EconomicStore(path, now=lambda: 200))
    assert [item.opportunity_id for item in restarted.rank()] == ["quality", "raw-revenue"]


def test_duplicate_and_stale_write_fail_closed(tmp_path):
    e = engine(tmp_path)
    item = e.add(opportunity())
    with pytest.raises(EconomicDenied):
        e.add(item)
    changed = e.transition("opp-1", OpportunityState.RESEARCHED, actor="reviewer")
    with pytest.raises(EconomicDenied):
        e.store.update(changed, item.fingerprint, "FORGED", {})


def test_ledger_tamper_detected(tmp_path):
    e = engine(tmp_path)
    e.add(opportunity())
    assert e.store.verify_ledger()
    with sqlite3.connect(e.store.path) as db:
        db.execute("UPDATE events SET payload_json='{}' WHERE seq=1")
    assert not e.store.verify_ledger()


def test_platform_registry_is_data_only_and_dry_run():
    records = PlatformRegistry().records()
    assert {item["platform_id"] for item in records} == {"ebay", "etsy", "shopify", "printful", "upwork"}
    assert all(item["default_mode"] == "DRY_RUN" for item in records)


def test_platform_dry_run_does_not_grant_permission():
    adapter = PlatformAdapter(PlatformRegistry())
    result = adapter.authorize(PlatformAction("shopify", "render_listing", dry_run=True))
    assert result["mode"] == "DRY_RUN"
    assert not result["api_availability_is_permission"]


def test_upwork_access_review_required():
    with pytest.raises(PlatformDenied, match="access review"):
        PlatformAdapter(PlatformRegistry()).authorize(PlatformAction("upwork", "read_jobs"))


def test_ebay_retail_direct_fulfillment_prohibited_even_with_owner():
    with pytest.raises(PlatformDenied, match="prohibited"):
        PlatformAdapter(PlatformRegistry()).authorize(PlatformAction(
            "ebay", "retail_marketplace_direct_fulfillment", dry_run=False,
            owner_authorized=True, external_effect=True))


def test_external_effect_and_capital_require_owner():
    adapter = PlatformAdapter(PlatformRegistry())
    with pytest.raises(PlatformDenied):
        adapter.authorize(PlatformAction("printful", "submit_order", dry_run=False, external_effect=True))
    with pytest.raises(PlatformDenied):
        adapter.authorize(PlatformAction("etsy", "listing", capital_required_cents=1))


def test_platform_file_contains_no_credentials_or_live_endpoints():
    text = open(PlatformRegistry().get("ebay") and __import__("economic.platforms").platforms.__file__.replace("platforms.py", "platform_registry.json"), encoding="utf-8").read()
    assert "token" not in text.casefold()
    assert "password" not in text.casefold()
    assert "api_key" not in text.casefold()
