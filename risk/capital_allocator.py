#!/usr/bin/env python3
"""DARWIN ZERO-0 Risk and Capital Manager

Provides dynamic risk sizing and capital allocation logic per the DARWIN
ZERO-0 Financial Policy. All amounts in cents to avoid floating point.

Policy constraints (from FINANCIAL_POLICY.md):
- No debt, interest, leverage, futures, CFDs, short selling, betting, gambling
- Paid upgrades require positive expected economic value vs free/build alternatives
- Capital allocation considers: expected value, maximum loss, liquidity,
  survival, time, evidence, opportunity cost, reputation, reversibility
- Risk is sized dynamically; high upside does not justify all-in exposure
"""
import json
import os
from pathlib import Path

from core.statemanager import append_ledger_entry, append_event, load_state, save_state
from events.event_model import EventDispatcher, EventType


class CapitalAllocator:
    """Dynamic capital allocator per DARWIN ZERO-0 Financial Policy.

    Allocates capital based on expected value, risk, and policy constraints.
    Never allocates more than available current capital. Always preserves
    reserve for survival/liquidity.
    """

    def __init__(self):
        self.state_path = Path(__file__).parent.parent / "state" / "state.json"
        self.dispatcher = EventDispatcher()

    def allocate(self, ev_cents, risk, capital_requested_cents, description,
                 source="risk_capital_agent", reviewer_verdict=None):
        """Allocate capital considering EV, risk, and policy constraints.

        Args:
            ev_cents: Expected value in cents (may be negative)
            risk: Risk score 0-100
            capital_requested_cents: Capital requested in cents
            description: Allocation description
            source: Emitting component
            reviewer_verdict: Reviewer recommendation (approved/rejected/paused)

        Returns:
            Dict with allocation result
        """
        state = load_state()
        if state is None:
            from core.statemanager import init_state as _init
            _init()
            state = load_state()

        current_cents = state["capital"]["current_cents"]
        reserve_cents = state["capital"]["reserve_cents"]
        owner_supplied = state["capital"]["owner_supplied_cents"]

        # Policy: never allocate more than current capital + owner-supplied
        # (but owner-supplied is $0 for ZERO-0, so we use current_cents only)
        available_non_reserve = current_cents - reserve_cents
        if available_non_reserve < 0:
            available_non_reserve = 0

        # Policy: preserve reserve for survival/liquidity
        # Reserve should be at least 10% of current capital or a minimum floor
        reserve_floor = max(100, int(current_cents * 0.1))  # 10% or $1 min
        allocatable = current_cents - reserve_floor

        # Risk sizing: the higher the risk, the less capital we allocate
        # Simple risk-adjusted sizing: allocation = requested * (1 - risk/100)
        # But cap at allocatable maximum
        risk_factor = 1 - (risk / 100.0)
        # Ensure risk_factor is between 0.1 (90% risk) and 1.0 (0% risk)
        risk_factor = max(0.1, min(1.0, risk_factor))

        # Risk-adjusted requested capital
        risk_adjusted_request = int(capital_requested_cents * risk_factor)

        # Final allocation: minimum of risk-adjusted request and allocatable
        final_allocation = min(risk_adjusted_request, allocatable)

        # If EV is negative, reject outright (per policy: paid upgrades require +EV)
        if ev_cents < 0:
            verdict = "rejected"
            final_allocation = 0
            reason = "Negative expected value; policy prohibits allocation"
        # If requested exceeds allocatable, reject or trim
        elif capital_requested_cents > allocatable:
            verdict = "rejected" if capital_requested_cents > current_cents else "paused"
            reason = f"Requested {capital_requested_cents}c exceeds allocatable {allocatable}c"
            final_allocation = allocatable if allocatable > 0 else 0
        else:
            verdict = "approved" if final_allocation > 0 else "rejected"
            reason = "Allocation approved within risk constraints"

        # Apply reviewer verdict if provided
        if reviewer_verdict:
            verdict = reviewer_verdict

        result = {
            "decision": verdict,
            "allocated_cents": final_allocation,
            "requested_cents": capital_requested_cents,
            "ev_cents": ev_cents,
            "risk": risk,
            "allocatable_cents": allocatable,
            "reserve_cents": reserve_cents,
            "reason": reason,
        }

        # Dispatch event
        self.dispatcher.capital_allocation_proposed(
            ev_cents=ev_cents,
            risk=risk,
            capital_requested_cents=capital_requested_cents,
            source=source,
            reviewer_verdict=reviewer_verdict,
            final_decision=verdict,
        )

        # Record ledger entry if allocated
        if final_allocation > 0 and verdict == "approved":
            entry = {
                "id": f"ledger_alloc_{result['id']}" if False else f"ledger_alloc_{uuid4_str()}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "capital_allocation",
                "amount_cents": final_allocation,
                "description": description,
            }
            append_ledger_entry(entry)

        return result


def uuid4_str():
    """Generate a short UUID-like string for ledger entries."""
    import uuid
    return str(uuid.uuid4())[:8]


# Convenience function for common allocation pattern
def allocate_for_opportunity(ev_cents, risk, capital_required_cents, opportunity_id,
                             source="risk_capital_agent"):
    """Allocate capital for an opportunity with standard risk sizing.

    Args:
        ev_cents: Expected value in cents
        risk: Risk score 0-100
        capital_required_cents: Capital required to pursue opportunity
        opportunity_id: Link to the opportunity
        source: Emitting component

    Returns:
        Allocation result dict
    """
    allocator = CapitalAllocator()
    return allocator.allocate(
        ev_cents=ev_cents,
        risk=risk,
        capital_requested_cents=capital_required_cents,
        description=f"Capital allocation for opportunity {opportunity_id}",
        source=source,
    )