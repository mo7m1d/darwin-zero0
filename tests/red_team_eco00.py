import sqlite3

import pytest

from economic import (EconomicAmounts, EconomicDenied, EconomicEngine, EconomicStore,
                      Opportunity, OpportunityState, PlatformAction, PlatformAdapter,
                      PlatformRegistry, default_capability_registry)
from economic.model import EconomicValueError, MAX_INT
from economic.platforms import PlatformDenied


def make(tmp_path, capital=0):
    item = Opportunity("attack", "cross_marketplace_resale", "attack",
                       EconomicAmounts(1000, marketplace_fees_cents=100,
                                       capital_required_cents=capital,
                                       uncertainty_bps=500, policy_risk_bps=500,
                                       execution_risk_bps=500, evidence_confidence_bps=8000),
                       capital_components_cents={} if not capital else {"inventory": capital})
    engine = EconomicEngine(default_capability_registry(), EconomicStore(tmp_path / "eco.sqlite3", now=lambda: 1))
    engine.add(item)
    return engine


@pytest.mark.parametrize("value", [-1, 1.5, True, MAX_INT + 1])
def test_red_negative_float_bool_overflow_money(value):
    with pytest.raises(EconomicValueError):
        EconomicAmounts(value)


@pytest.mark.parametrize("field", ["uncertainty_bps", "policy_risk_bps", "execution_risk_bps", "evidence_confidence_bps"])
def test_red_invalid_bps(field):
    with pytest.raises(EconomicValueError):
        EconomicAmounts(1, **{field: 10001})


@pytest.mark.parametrize("target", [OpportunityState.SCORED, OpportunityState.EXECUTION_READY,
                                     OpportunityState.EXECUTING, OpportunityState.ACCEPTED])
def test_red_state_jump(tmp_path, target):
    with pytest.raises(EconomicDenied):
        make(tmp_path).transition("attack", target, actor="llm", owner_authorized=True,
                                  acceptance_verified=True, evidence_ref="fake", acceptance_hash="a" * 64)


@pytest.mark.parametrize("actor", ["llm", "agent", "platform", "owner-looking-user", "model"])
def test_red_fake_acceptance_actor(tmp_path, actor):
    e = make(tmp_path)
    for state in (OpportunityState.RESEARCHED, OpportunityState.POLICY_CHECKED,
                  OpportunityState.SCORED, OpportunityState.CANDIDATE,
                  OpportunityState.DRY_RUN_READY, OpportunityState.EXECUTION_READY):
        e.transition("attack", state, actor="reviewer", evidence_ref="e://x")
    e.transition("attack", OpportunityState.EXECUTING, actor="owner", owner_authorized=True,
                 owner_approval_ref="owner://execute", owner_approval_hash="b" * 64)
    e.transition("attack", OpportunityState.ACCEPTANCE_PENDING, actor="executor")
    with pytest.raises(EconomicDenied):
        e.transition("attack", OpportunityState.ACCEPTED, actor=actor,
                     acceptance_verified=True, evidence_ref="plain-text-pass", acceptance_hash="a" * 64)


@pytest.mark.parametrize("component", ["purchase", "acquisition", "deposit", "fulfillment", "inventory", "other"])
def test_red_capital_component_cannot_be_hidden(component):
    with pytest.raises(EconomicValueError):
        Opportunity("x", "software_delivery", "x", EconomicAmounts(100, capital_required_cents=0),
                    capital_components_cents={component: 1})


def test_red_positive_capital_without_owner(tmp_path):
    e = make(tmp_path, 1)
    for state in (OpportunityState.RESEARCHED, OpportunityState.POLICY_CHECKED,
                  OpportunityState.SCORED, OpportunityState.CANDIDATE,
                  OpportunityState.DRY_RUN_READY):
        e.transition("attack", state, actor="reviewer", evidence_ref="e://x")
    with pytest.raises(EconomicDenied):
        e.transition("attack", OpportunityState.EXECUTION_READY, actor="llm")


def test_red_bare_owner_boolean_is_not_provenance(tmp_path):
    e = make(tmp_path, 1)
    for state in (OpportunityState.RESEARCHED, OpportunityState.POLICY_CHECKED,
                  OpportunityState.SCORED, OpportunityState.CANDIDATE,
                  OpportunityState.DRY_RUN_READY):
        e.transition("attack", state, actor="reviewer", evidence_ref="e://x")
    with pytest.raises(EconomicDenied):
        e.transition("attack", OpportunityState.EXECUTION_READY, actor="owner", owner_authorized=True)


def test_red_raw_revenue_ranking_attack(tmp_path):
    e = make(tmp_path)
    other = Opportunity("safe", "software_delivery", "safe",
                        EconomicAmounts(900, marketplace_fees_cents=10, uncertainty_bps=0,
                                        evidence_confidence_bps=10000))
    e.add(other)
    for identity in ("attack", "safe"):
        e.transition(identity, OpportunityState.RESEARCHED, actor="reviewer")
        e.transition(identity, OpportunityState.POLICY_CHECKED, actor="reviewer", evidence_ref="e://p")
        e.transition(identity, OpportunityState.SCORED, actor="reviewer", evidence_ref="e://s")
    assert e.rank()[0].opportunity_id == "safe"


def test_red_restart_does_not_change_rank(tmp_path):
    e = make(tmp_path)
    e.transition("attack", OpportunityState.RESEARCHED, actor="reviewer")
    e.transition("attack", OpportunityState.POLICY_CHECKED, actor="reviewer", evidence_ref="e://p")
    e.transition("attack", OpportunityState.SCORED, actor="reviewer", evidence_ref="e://s")
    assert EconomicEngine(default_capability_registry(), EconomicStore(e.store.path)).rank()[0].fingerprint == e.rank()[0].fingerprint


def test_red_ledger_tamper(tmp_path):
    e = make(tmp_path)
    with sqlite3.connect(e.store.path) as db:
        db.execute("UPDATE events SET event_hash=?", ("0" * 64,))
    assert not e.store.verify_ledger()


@pytest.mark.parametrize("action", [
    PlatformAction("upwork", "assume_account"),
    PlatformAction("ebay", "retail_marketplace_direct_fulfillment"),
    PlatformAction("printful", "submit_order", dry_run=False, external_effect=True),
    PlatformAction("etsy", "publish_listing", dry_run=False, external_effect=True),
    PlatformAction("shopify", "charge", capital_required_cents=1),
])
def test_red_platform_permission_bypass(action):
    with pytest.raises(PlatformDenied):
        PlatformAdapter(PlatformRegistry()).authorize(action)


def test_red_api_availability_never_permission():
    result = PlatformAdapter(PlatformRegistry()).authorize(PlatformAction("ebay", "validate", dry_run=True))
    assert result["api_availability_is_permission"] is False
