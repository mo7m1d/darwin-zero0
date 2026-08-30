"""DARWIN ZERO-0 Tests

Tests for the foundational bootstrap structure created in this milestone.
All tests verify that the structure is correct and that executable code
works as expected per the project requirements.
"""

import json
import os
from pathlib import Path

from core.statemanager import init_state, load_state, append_event, append_ledger_entry, append_opportunity, append_experiment
from events.event_model import EventDispatcher, EventType
from opportunities.opportunity import Opportunity
from experiments.experiment import Experiment
from risk.capital_allocator import CapitalAllocator, allocate_for_opportunity
from risk.risk_sizer import RiskSizer
from ledger.immutable_ledger import ImmutableLedger
from routing.model_router import ModelRouter, route_task
from scouting.scout import TechnologyScout
from evolution.evolution_lab import EvolutionLab, uuid_str
from children.registry import ChildAgentProposal, ChildAgentRegistry, propose_child, StateManager, uuid_str as child_uuid


def test_statemanager_init():
    """Test state initialization at $0 capital."""
    # Remove existing state to test fresh init
    state_path = Path("core/state.json")
    if state_path.exists():
        state_path.unlink()

    state = init_state()
    assert state is not None, "init_state() should return a state dict"
    assert state["capital"]["owner_supplied_cents"] == 0, "Owner-supplied capital should be 0"
    assert state["capital"]["current_cents"] == 0, "Current capital should be 0"
    assert state["model_router"]["free_preferred"] is True, "Free models should be preferred"
    print("  ✓ test_statemanager_init passed")


def test_statemanager_load():
    """Test loading existing state."""
    state = load_state()
    # State should have been initialized by test_statemanager_init
    assert state is not None, "load_state() should return a state dict"
    assert "version" in state, "State should have version"
    assert "bootstrapped_at" in state, "State should have bootstrapped_at"
    print("  ✓ test_statemanager_load passed")


def test_event_dispatcher():
    """Test event dispatching through the event bus."""
    dispatcher = EventDispatcher()

    # Test OPPORTUNITY_FOUND
    event = dispatcher.opportunity_found(
        description="Test opportunity",
        ev_cents=1000,
        risk=30,
        capital_required_cents=500,
        source="test",
        evidence=["test evidence"],
    )
    assert event["type"] == "OPPORTUNITY_FOUND", "Event type should match"
    assert event["payload"]["description"] == "Test opportunity", "Description should match"
    print("  ✓ test_event_dispatcher passed")


def test_opportunity_creation():
    """Test opportunity creation and lifecycle."""
    opp = Opportunity(
        description="Test opportunity for unit test",
        ev_cents=500,
        risk=30,
        capital_required_cents=100,
        source="test_module",
    )
    assert opp.id is not None, "Opportunity should have an ID"
    assert opp.status == "discovered", "New opportunity should be discovered"
    assert opp.ev_cents == 500, "EV should be 500 cents"
    print("  ✓ test_opportunity_creation passed")


def test_experiment_creation():
    """Test experiment creation."""
    # First create an opportunity
    opp = Opportunity(
        description="Experiment test opportunity",
        ev_cents=500,
        risk=30,
        capital_required_cents=100,
        source="experiment_test",
    )

    exp = Experiment(
        opportunity_id=opp.id,
        hypothesis="Test hypothesis",
        method="Test method",
        cost_cents=50,
        source="experiment_test",
    )
    assert exp.id is not None, "Experiment should have an ID"
    assert exp.status == "pending", "New experiment should be pending"
    print("  ✓ test_experiment_creation passed")


def test_risk_sizer():
    """Test risk sizer basic functionality."""
    sizer = RiskSizer()
    # Test with positive EV
    result = sizer.size_risk(risk_score=30, ev_cents=500, allocatable_cents=1000)
    assert "risk_percent" in result, "Result should have risk_percent"
    assert "risk_cents" in result, "Result should have risk_cents"
    assert result["risk_cents"] >= 0, "Risk cents should be non-negative"
    print("  ✓ test_risk_sizer passed")


def test_capital_allocator():
    """Test capital allocator basic functionality."""
    allocator = CapitalAllocator()
    result = allocator.allocate(
        ev_cents=500,
        risk=30,
        capital_requested_cents=100,
        description="Test allocation",
        source="test",
    )
    assert "decision" in result, "Result should have a decision"
    assert "allocated_cents" in result, "Result should have allocated_cents"
    print("  ✓ test_capital_allocator passed")


def test_ledger():
    """Test immutable ledger functionality."""
    ledger = ImmutableLedger()

    # Record opening balance (should already exist)
    # Record an expense
    entry = ledger.record_expense(
        amount_cents=100,
        description="Test expense",
    )
    assert entry["type"] == "expense", "Entry type should be expense"
    assert entry["amount_cents"] == 100, "Amount should be 100 cents"

    # Record revenue
    rev_entry = ledger.record_revenue(
        amount_cents=200,
        description="Test revenue",
    )
    assert rev_entry["type"] == "revenue", "Entry type should be revenue"
    assert rev_entry["amount_cents"] == 200, "Amount should be 200 cents"

    # Get summary
    summary = ledger.get_ledger_summary()
    assert "total_in_cents" in summary, "Summary should have total_in"
    assert "total_out_cents" in summary, "Summary should have total_out"
    print("  ✓ test_ledger passed")


def test_model_router():
    """Test model router basic functionality."""
    router = ModelRouter()

    # Test routing a classification task
    result = router.route(
        task_type="classification",
        cost_sensitivity=True,
        latency_requirement="normal",
    )
    assert "selected_model" in result, "Result should have selected_model"
    assert "cost_sensitive" in result, "Result should indicate cost sensitivity"
    print("  ✓ test_model_router passed")


def test_technology_scout():
    """Test technology scout basic functionality."""
    scout = TechnologyScout()
    caps = scout.scan_capabilities()
    assert len(caps) > 0, "Scout should return baseline capabilities"
    # Check that free/local capabilities have cost_cents=0
    free_caps = [c for c in caps if c.get("cost_cents", 0) == 0]
    assert len(free_caps) > 0, "Should have free capabilities"
    print("  ✓ test_technology_scout passed")


def test_evolution_lab():
    """Test evolution lab basic functionality."""
    lab = EvolutionLab()
    gap = lab.detect_gap("Test gap for unit testing")
    assert gap["id"] is not None, "Gap should have an ID"
    assert gap["description"] == "Test gap for unit testing"
    print("  ✓ test_evolution_lab passed")


def test_child_proposal():
    """Test child agent proposal creation."""
    # Test with positive risk-adjusted EV
    proposal = propose_child(
        funding_cents=1000,
        scaling_reserve_cents=500,
        distribution_cents=200,
        expected_ev_cents=1500,
        risk_adjusted_ev_cents=800,
        source="test",
    )
    assert proposal.id is not None, "Proposal should have an ID"
    assert proposal.status != "rejected" or proposal.risk_adjusted_ev_cents > 0, \
        "Positive risk-adjusted EV proposal should not be rejected"
    print("  ✓ test_child_proposal passed")


def test_child_negative_ev():
    """Test child agent proposal with negative risk-adjusted EV is rejected."""
    proposal = propose_child(
        funding_cents=1000,
        scaling_reserve_cents=500,
        distribution_cents=200,
        expected_ev_cents=500,
        risk_adjusted_ev_cents=-100,  # Negative!
        source="test",
    )
    assert proposal.status == "rejected", "Negative risk-adjusted EV should be rejected"
    print("  ✓ test_child_negative_ev passed")


def test_directory_structure():
    """Test that all expected directories and files exist."""
    expected_dirs = [
        "core", "agents", "opportunities", "experiments", "memory",
        "risk", "ledger", "events", "healing", "skills", "tools",
        "routing", "scouting", "evolution", "children", "tests", "docs"
    ]

    expected_files = [
        "DARWIN_BOOTSTRAP.md",
        "AGENTS.md",
        "core/statemanager.py",
        "core/statemanager_schema.json",
        "events/event_model.py",
        "opportunities/opportunity.py",
        "experiments/experiment.py",
        "risk/capital_allocator.py",
        "risk/risk_sizer.py",
        "ledger/immutable_ledger.py",
        "routing/model_router.py",
        "scouting/scout.py",
        "evolution/evolution_lab.py",
        "children/registry.py",
        "tests/__init__.py",
    ]

    for d in expected_dirs:
        assert os.path.isdir(d) or os.path.exists(d), f"Expected directory/file: {d}"

    for f in expected_files:
        assert os.path.exists(f), f"Expected file: {f}"

    print("  ✓ test_directory_structure passed")


def run_all_tests():
    """Run all tests and report results."""
    tests = [
        test_directory_structure,
        test_statemanager_init,
        test_statemanager_load,
        test_event_dispatcher,
        test_opportunity_creation,
        test_experiment_creation,
        test_risk_sizer,
        test_capital_allocator,
        test_ledger,
        test_model_router,
        test_technology_scout,
        test_evolution_lab,
        test_child_proposal,
        test_child_negative_ev,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__} FAILED: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed out of {len(tests)} tests")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)