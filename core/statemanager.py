#!/usr/bin/env python3
"""DARWIN ZERO-0 State Manager

Manages the machine-readable state foundation for ZERO-0, bootstrapped at $0 capital.
Provides load/create/init functions for the ZERO-0 state schema.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    from .statemanager_schema import (
        capital_required_fields,
        model_router_required_fields,
    )
except ImportError:
    capital_required_fields = ["owner_supplied_cents", "current_cents"]
    model_router_required_fields = ["default_model", "free_preferred", "cost_cap_cents"]

STATE_DIR = Path(__file__).parent
STATE_PATH = STATE_DIR / "state.json"


def init_state():
    """Initialize ZERO-0 state at $0 capital.

    Creates the state.json with opening balance and defaults.
    Must be called once at boot. Idempotent: if state.json already exists
    with valid structure, does nothing.
    """
    if STATE_PATH.exists():
        # Verify it's valid schema; if not, overwrite
        try:
            with open(STATE_PATH, "r") as f:
                state = json.load(f)
            # Check required fields exist
            if (
                "version" in state
                and "bootstrapped_at" in state
                and "capital" in state
                and "model_router" in state
                and state["capital"].get("owner_supplied_cents") is not None
                and state["model_router"].get("default_model") is not None
            ):
                return  # Valid state already exists
        except (json.JSONDecodeError, KeyError, TypeError):
            pass  # Fall through to overwrite

    opening_balance = {
        "id": "ledger_opening_balance",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "opening_balance",
        "amount_cents": 0,
        "description": "DARWIN ZERO-0 opening balance: $0 owner-supplied business capital",
    }

    state = {
        "version": "0.1.0",
        "bootstrapped_at": datetime.now(timezone.utc).isoformat(),
        "capital": {
            "owner_supplied_cents": 0,
            "current_cents": 0,
            "reserve_cents": 0,
            "child_agent_fund_cents": 0,
        },
        "model_router": {
            "default_model": "nemotron-3.5-lightning-free",
            "free_preferred": True,
            "cost_cap_cents": 1000,  # $10 cost cap before review
        },
        "events": [],
        "incidents": [],
        "ledger": [opening_balance],
        "opportunities": [],
        "experiments": [],
        "capabilities": [],
        "children": [],
    }

    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)

    print(f"DARWIN ZERO-0 state initialized at {STATE_PATH}")
    return state


def load_state():
    """Load existing ZERO-0 state from state.json.

    Returns the state dict, or None if file doesn't exist.
    """
    if not STATE_PATH.exists():
        return None
    try:
        with open(STATE_PATH, "r") as f:
            state = json.load(f)
        return state
    except json.JSONDecodeError:
        print(f"WARNING: state.json at {STATE_PATH} is not valid JSON")
        return None


def append_event(event_dict):
    """Append a dispatched event to the state's event log.

    Args:
        event_dict: Dict matching the event model schema (with 'type' and 'payload')
    """
    state = load_state()
    if state is None:
        init_state()
        state = load_state()
    event_dict["id"] = event_dict.get("id", f"event_{len(state.get('events', [])) + 1}")
    state["events"].append(event_dict)
    save_state(state)


def append_ledger_entry(entry_dict):
    """Append an immutable ledger entry.

    Args:
        entry_dict: Dict matching the ledger_entry schema
    """
    state = load_state()
    if state is None:
        init_state()
        state = load_state()
    entry_dict["id"] = entry_dict.get("id", f"ledger_{len(state.get('ledger', [])) + 1}")
    # Verify amount_cents is present
    if "amount_cents" not in entry_dict:
        raise ValueError("ledger_entry must contain amount_cents")
    state["ledger"].append(entry_dict)
    save_state(state)


def append_opportunity(opp_dict):
    """Append an opportunity to the opportunities heap."""
    state = load_state()
    if state is None:
        init_state()
        state = load_state()
    opp_dict["id"] = opp_dict.get("id", f"opp_{len(state.get('opportunities', [])) + 1}")
    state["opportunities"].append(opp_dict)
    save_state(state)


def append_experiment(exp_dict):
    """Append an experiment to the experiments heap."""
    state = load_state()
    if state is None:
        init_state()
        state = load_state()
    exp_dict["id"] = exp_dict.get("id", f"exp_{len(state.get('experiments', [])) + 1}")
    state["experiments"].append(exp_dict)
    save_state(state)


def append_capability(cap_dict):
    """Append a discovered capability."""
    state = load_state()
    if state is None:
        init_state()
        state = load_state()
    cap_dict["id"] = cap_dict.get("id", f"cap_{len(state.get('capabilities', [])) + 1}")
    state["capabilities"].append(cap_dict)
    save_state(state)


def append_child(child_dict):
    """Append a child agent to the registry."""
    state = load_state()
    if state is None:
        init_state()
        state = load_state()
    child_dict["id"] = child_dict.get("id", f"child_{len(state.get('children', [])) + 1}")
    state["children"].append(child_dict)
    save_state(state)


def save_state(state):
    """Persist state to state.json."""
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def reset_state():
    """Reset state to $0 bootstrapped defaults. Use only for testing."""
    state = {
        "version": "0.1.0",
        "bootstrapped_at": datetime.now(timezone.utc).isoformat(),
        "capital": {
            "owner_supplied_cents": 0,
            "current_cents": 0,
            "reserve_cents": 0,
            "child_agent_fund_cents": 0,
        },
        "model_router": {
            "default_model": "nemotron-3.5-lightning-free",
            "free_preferred": True,
            "cost_cap_cents": 1000,
        },
        "events": [],
        "incidents": [],
        "ledger": [
            {
                "id": "ledger_opening_balance",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "opening_balance",
                "amount_cents": 0,
                "description": "DARWIN ZERO-0 opening balance: $0 owner-supplied business capital",
            }
        ],
        "opportunities": [],
        "experiments": [],
        "capabilities": [],
        "children": [],
    }
    save_state(state)
    print("DARWIN ZERO-0 state reset to bootstrapped defaults")


if __name__ == "__main__":
    # Initialize when run directly
    init_state()
    # Show the state
    state = load_state()
    print(json.dumps(state, indent=2))