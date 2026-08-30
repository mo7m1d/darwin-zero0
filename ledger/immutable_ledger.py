#!/usr/bin/env python3
"""DARWIN ZERO-0 Immutable Ledger

Provides an append-only immutable ledger for all financial transactions.
Per the Constitution and Financial Policy, only trusted accounting/payment
sources may confirm revenue or balances. LLM estimates are not financial truth.

All entries are immutable — never mutate prior entries. Only append.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.statemanager import append_ledger_entry, load_state, save_state


class ImmutableLedger:
    """Immutable append-only ledger for DARWIN ZERO-0.

    Constraints per FINANCIAL_POLICY.md and DARWIN_CONSTITUTION.md:
    - Only trusted accounting/payment sources may confirm revenue/balances
    - LLM estimates are NOT financial truth
    - Every confirmed receipt and expense must enter the immutable ledger
    - Ledger entries are never mutated; only appended
    - Owner controls audit logs, rollback, pause, freeze, and termination
    """

    def __init__(self):
        self.state_path = Path(__file__).parent.parent / "state" / "state.json"

    def record_expense(self, amount_cents, description, reference_id=None):
        """Record an expense in the immutable ledger.

        Args:
            amount_cents: Expense amount in cents (positive number, type='expense')
            description: Human-readable expense description
            reference_id: Optional link to opportunity_id, experiment_id, etc.

        Returns:
            The created ledger entry dict
        """
        entry = {
            "id": f"ledger_exp_{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "expense",
            "amount_cents": amount_cents,
            "description": description,
        }
        if reference_id:
            entry["reference_id"] = reference_id

        append_ledger_entry(entry)
        return entry

    def record_revenue(self, amount_cents, description, reference_id=None):
        """Record revenue in the immutable ledger.

        Args:
            amount_cents: Revenue amount in cents (positive number, type='revenue')
            description: Human-readable revenue description
            reference_id: Optional link to opportunity_id, experiment_id, etc.

        Returns:
            The created ledger entry dict
        """
        entry = {
            "id": f"ledger_rev_{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "revenue",
            "amount_cents": amount_cents,
            "description": description,
        }
        if reference_id:
            entry["reference_id"] = reference_id

        append_ledger_entry(entry)
        return entry

    def record_capital_allocation(self, amount_cents, description, reference_id=None):
        """Record a capital allocation in the ledger.

        Args:
            amount_cents: Allocated amount in cents (positive number, type='capital_allocation')
            description: Allocation description
            reference_id: Optional link to opportunity_id or experiment_id

        Returns:
            The created ledger entry dict
        """
        entry = {
            "id": f"ledger_alloc_{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "capital_allocation",
            "amount_cents": amount_cents,
            "description": description,
        }
        if reference_id:
            entry["reference_id"] = reference_id

        append_ledger_entry(entry)
        return entry

    def record_opening_balance(self):
        """Record the opening balance entry ($0 for ZERO-0)."""
        entry = {
            "id": "ledger_opening_balance",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "opening_balance",
            "amount_cents": 0,
            "description": "DARWIN ZERO-0 opening balance: $0 owner-supplied business capital",
        }
        append_ledger_entry(entry)
        return entry

    def get_ledger(self):
        """Return the full ledger from state."""
        state = load_state()
        return state.get("ledger", []) if state else []

    def get_ledger_summary(self):
        """Return a summary of the ledger: total in, total out, net."""
        ledger = self.get_ledger()
        total_in = sum(e["amount_cents"] for e in ledger if e["type"] in ("revenue", "opening_balance", "capital_allocation"))
        total_out = abs(sum(e["amount_cents"] for e in ledger if e["type"] == "expense"))
        net = total_in - total_out
        return {
            "total_in_cents": total_in,
            "total_out_cents": total_out,
            "net_cents": net,
            "entry_count": len(ledger),
        }


def uuid4_hex8():
    """Generate 8-char hex string for ledger entry IDs."""
    return uuid.uuid4().hex[:8]