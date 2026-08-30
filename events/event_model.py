#!/usr/bin/env python3
"""DARWIN ZERO-0 Event Model and Dispatcher

Defines the core event types and provides a dispatch mechanism for all major
system events. Events flow through the event bus and can be subscribed to
for logging, monitoring, or automatic handling (e.g., incident detection →
self-healing loop).

All major events follow this model:
- id: UUID
- type: one of the defined event type enum values
- timestamp: ISO datetime
- source: string identifying the emitting component
- payload: event-specific data matching the type

The EventDispatcher maintains the event log in state and broadcasts to
registered listeners.
"""

import json
import uuid
import os
from datetime import datetime, timezone
from pathlib import Path

# Import from core.statemanager (same-level package)
from core.statemanager import append_event, load_state, save_state

EVENTS_DIR = Path(__file__).parent
STATE_PATH = EVENTS_DIR.parent / "state" / "state.json" if (EVENTS_DIR.parent / "state" / "state.json").exists() else None


class EventType:
    """Enumeration of all DARWIN ZERO-0 event types."""

    OPPORTUNITY_FOUND = "OPPORTUNITY_FOUND"
    EXPERIMENT_STARTED = "EXPERIMENT_STARTED"
    EXPERIMENT_SUCCEEDED = "EXPERIMENT_SUCCEEDED"
    EXPERIMENT_FAILED = "EXPERIMENT_FAILED"
    BUILD_FAILED = "BUILD_FAILED"
    INCIDENT_DETECTED = "INCIDENT_DETECTED"
    CAPABILITY_DISCOVERED = "CAPABILITY_DISCOVERED"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    CAPITAL_ALLOCATION_PROPOSED = "CAPITAL_ALLOCATION_PROPOSED"
    REPRODUCTION_PROPOSED = "REPRODUCTION_PROPOSED"


# Default payload schemas per event type (for documentation/validation)
PAYLOAD_SCHEMAS = {
    EventType.OPPORTUNITY_FOUND: {
        "required": ["description", "ev_cents", "risk", "capital_required_cents"],
        "properties": {
            "description": {"type": "string"},
            "ev_cents": {"type": "integer", "minimum": -1000000, "maximum": 1000000},
            "risk": {"type": "integer", "minimum": 0, "maximum": 100},
            "capital_required_cents": {"type": "integer", "minimum": 0},
            "source": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
        },
    },
    EventType.EXPERIMENT_STARTED: {
        "required": ["opportunity_id", "hypothesis", "method", "cost_cents"],
        "properties": {
            "opportunity_id": {"type": "string"},
            "hypothesis": {"type": "string"},
            "method": {"type": "string"},
            "cost_cents": {"type": "integer", "minimum": 0},
            "status": {"type": "string", "enum": ["pending", "running"]},
        },
    },
    EventType.EXPERIMENT_SUCCEEDED: {
        "required": ["opportunity_id", "result", "capital_returned_cents"],
        "properties": {
            "opportunity_id": {"type": "string"},
            "result": {"type": "string"},
            "learnings": {"type": "array", "items": {"type": "string"}},
            "capital_returned_cents": {"type": "integer", "minimum": 0},
        },
    },
    EventType.EXPERIMENT_FAILED: {
        "required": ["opportunity_id", "error", "capital_lost_cents"],
        "properties": {
            "opportunity_id": {"type": "string"},
            "error": {"type": "string"},
            "lessons": {"type": "array", "items": {"type": "string"}},
            "capital_lost_cents": {"type": "integer", "minimum": 0},
        },
    },
    EventType.BUILD_FAILED: {
        "required": ["component", "error"],
        "properties": {
            "component": {"type": "string"},
            "error": {"type": "string"},
            "retry_count": {"type": "integer", "minimum": 0, "default": 0},
            "status": {"type": "string"},
        },
    },
    EventType.INCIDENT_DETECTED: {
        "required": ["signature", "severity"],
        "properties": {
            "signature": {"type": "string"},
            "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            "auto_healable": {"type": "boolean"},
            "source": {"type": "string"},
        },
    },
    EventType.CAPABILITY_DISCOVERED: {
        "required": ["name", "cost_cents"],
        "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "cost_cents": {"type": "integer", "minimum": 0},
            "source": {"type": "string"},
            "status": {"type": "string", "enum": ["available", "evaluating"]},
        },
    },
    EventType.PAYMENT_CONFIRMED: {
        "required": ["source", "amount_cents", "receipt_id"],
        "properties": {
            "source": {"type": "string"},
            "amount_cents": {"type": "integer"},
            "receipt_id": {"type": "string"},
            "ledger_entry_id": {"type": "string"},
        },
    },
    EventType.CAPITAL_ALLOCATION_PROPOSED: {
        "required": ["ev_cents", "risk", "capital_requested_cents"],
        "properties": {
            "ev_cents": {"type": "integer", "minimum": -1000000, "maximum": 1000000},
            "risk": {"type": "integer", "minimum": 0, "maximum": 100},
            "capital_requested_cents": {"type": "integer", "minimum": 0},
            "reviewer_verdict": {"type": "string"},
            "final_decision": {"type": "string", "enum": ["approved", "rejected", "paused"]},
        },
    },
    EventType.REPRODUCTION_PROPOSED: {
        "required": [
            "funding_cents",
            "scaling_reserve_cents",
            "distribution_cents",
            "expected_ev_cents",
            "risk_adjusted_ev_cents",
        ],
        "properties": {
            "funding_cents": {"type": "integer", "minimum": 0},
            "scaling_reserve_cents": {"type": "integer", "minimum": 0},
            "distribution_cents": {"type": "integer", "minimum": 0},
            "expected_ev_cents": {"type": "integer"},
            "risk_adjusted_ev_cents": {"type": "integer"},
            "child_id": {"type": "string"},
            "proposal_id": {"type": "string"},
        },
    },
}


class EventDispatcher:
    """Dispatches DARWIN ZERO-0 events through the event bus.

    Responsibilities:
    - Create event objects with proper IDs and timestamps
    - Append events to the state event log via statemanager
    - Provide a registry pattern for listeners (callbacks)
    - Ensure all events flow through the immutable state layer
    """

    def __init__(self, state_path=None):
        self.listeners = []
        # Try to initialize state; if state doesn't exist, init it
        from core.statemanager import init_state as _init
        _init()
        self._ensure_state_path(state_path)

    def _ensure_state_path(self, override_path=None):
        """Ensure the state.json is accessible and initialized."""
        # statemanager.init_state() handles this; just make sure it runs
        pass

    def subscribe(self, callback):
        """Register a listener callback.

        Args:
            callback: Async or sync function accepting (event_dict)
        """
        self.listeners.append(callback)

    def unsubscribe(self, callback):
        """Unregister a listener callback."""
        if callback in self.listeners:
            self.listeners.remove(callback)

    def dispatch(self, event_type, payload=None, source="system"):
        """Dispatch an event through the bus.

        Args:
            event_type: EventType enum value
            payload: Dict with event-specific data (merged with defaults)
            source: String identifying the emitting component

        Returns:
            The created event dict (also appended to state)
        """
        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        event = {
            "id": event_id,
            "type": event_type,
            "timestamp": timestamp,
            "source": source,
            "payload": payload or {},
        }

        # Append to state event log
        append_event(event)

        # Notify all listeners
        for listener in self.listeners:
            try:
                listener(event)
            except Exception as e:
                print(f"WARNING: Event listener raised exception: {e}")

        return event

    # Convenience methods for each event type

    def opportunity_found(self, description, ev_cents, risk, capital_required_cents, source="opportunity_agent", evidence=None):
        """Dispatch OPPORTUNITY_FOUND event.

        Args:
            description: Human-readable opportunity description
            ev_cents: Expected value in cents (may be negative)
            risk: Risk score 0-100
            capital_required_cents: Capital required in cents
            source: Emitting component label
            evidence: List of evidence strings
        """
        payload = {
            "description": description,
            "ev_cents": ev_cents,
            "risk": risk,
            "capital_required_cents": capital_required_cents,
            "source": source,
        }
        if evidence:
            payload["evidence"] = evidence
        return self.dispatch(EventType.OPPORTUNITY_FOUND, payload, source)

    def experiment_started(self, opportunity_id, hypothesis, method, cost_cents, source="experiment orchestrator", status="pending"):
        """Dispatch EXPERIMENT_STARTED event.

        Args:
            opportunity_id: Link to the opportunity being tested
            hypothesis: Test hypothesis
            method: Experiment method/procedure
            cost_cents: Experiment cost in cents
            source: Emitting component
            status: Initial status (pending/running)
        """
        payload = {
            "opportunity_id": opportunity_id,
            "hypothesis": hypothesis,
            "method": method,
            "cost_cents": cost_cents,
            "status": status,
        }
        return self.dispatch(EventType.EXPERIMENT_STARTED, payload, source)

    def experiment_succeeded(self, opportunity_id, result, learnings=None, capital_returned_cents=0, source="experiment orchestrator"):
        """Dispatch EXPERIMENT_SUCCEEDED event.

        Args:
            opportunity_id: Link to the opportunity that was experimented on
            result: Experiment result summary
            learnings: List of learned lessons
            capital_returned_cents: Capital returned to ledger
            source: Emitting component
        """
        payload = {
            "opportunity_id": opportunity_id,
            "result": result,
            "learnings": learnnings or [],
            "capital_returned_cents": capital_returned_cents,
        }
        return self.dispatch(EventType.EXPERIMENT_SUCCEEDED, payload, source)

    def experiment_failed(self, opportunity_id, error, lessons=None, capital_lost_cents=0, source="experiment orchestrator"):
        """Dispatch EXPERIMENT_FAILED event.

        Args:
            opportunity_id: Link to the opportunity that failed
            error: Error description
            lessons: List of learned lessons
            capital_lost_cents: Capital lost in cents
            source: Emitting component
        """
        payload = {
            "opportunity_id": opportunity_id,
            "error": error,
            "lessons": lessons or [],
            "capital_lost_cents": capital_lost_cents,
        }
        return self.dispatch(EventType.EXPERIMENT_FAILED, payload, source)

    def build_failed(self, component, error, retry_count=0, source="build system"):
        """Dispatch BUILD_FAILED event.

        Args:
            component: Component that failed
            error: Error description
            retry_count: Number of retries attempted
            source: Emitting component
        """
        payload = {
            "component": component,
            "error": error,
            "retry_count": retry_count,
        }
        return self.dispatch(EventType.BUILD_FAILED, payload, source)

    def incident_detected(self, signature, severity, auto_healable=True, source="system"):
        """Dispatch INCIDENT_DETECTED event.

        Args:
            signature: Error/signature hash identifying the incident
            severity: "low" | "medium" | "high" | "critical"
            auto_healable: Whether the healing loop can attempt auto-fix
            source: Emitting component
        """
        payload = {
            "signature": signature,
            "severity": severity,
            "auto_healable": auto_healable,
        }
        return self.dispatch(EventType.INCIDENT_DETECTED, payload, source)

    def capability_discovered(self, name, description, cost_cents, source="scout", status="available"):
        """Dispatch CAPABILITY_DISCOVERED event.

        Args:
            name: Capability name
            description: Human-readable description
            cost_cents: Cost in cents (0 = free/local)
            source: Emitting component
            status: Initial status
        """
        payload = {
            "name": name,
            "description": description,
            "cost_cents": cost_cents,
            "source": source,
            "status": status,
        }
        return self.dispatch(EventType.CAPABILITY_DISCOVERED, payload, source)

    def payment_confirmed(self, source, amount_cents, receipt_id, ledger_entry_id=None):
        """Dispatch PAYMENT_CONFIRMED event.

        NOTE: Payment confirmation events should only be dispatched for verified
        trusted sources. LLM estimates are NOT financial truth per the Constitution.

        Args:
            source: Verified payment source
            amount_cents: Confirmed amount in cents
            receipt_id: Receipt/transaction ID
            ledger_entry_id: Link to ledger entry
        """
        payload = {
            "source": source,
            "amount_cents": amount_cents,
            "receipt_id": receipt_id,
        }
        if ledger_entry_id:
            payload["ledger_entry_id"] = ledger_entry_id
        return self.dispatch(EventType.PAYMENT_CONFIRMED, payload, source)

    def capital_allocation_proposed(self, ev_cents, risk, capital_requested_cents, source="risk_capital_agent", reviewer_verdict=None, final_decision=None):
        """Dispatch CAPITAL_ALLOCATION_PROPOSED event.

        Args:
            ev_cents: Expected value in cents
            risk: Risk score 0-100
            capital_requested_cents: Capital requested in cents
            source: Emitting component
            reviewer_verdict: Reviewer recommendation
            final_decision: final action (approved/rejected/paused)
        """
        payload = {
            "ev_cents": ev_cents,
            "risk": risk,
            "capital_requested_cents": capital_requested_cents,
            "source": source,
        }
        if reviewer_verdict is not None:
            payload["reviewer_verdict"] = reviewer_verdict
        if final_decision is not None:
            payload["final_decision"] = final_decision
        return self.dispatch(EventType.CAPITAL_ALLOCATION_PROPOSED, payload, source)

    def reproduction_proposed(self, funding_cents, scaling_reserve_cents, distribution_cents, expected_ev_cents, risk_adjusted_ev_cents, child_id=None, proposal_id=None, source="reproduction_manager"):
        """Dispatch REPRODUCTION_PROPOSED event.

        Args:
            funding_cents: Capital requested for child funding
            scaling_reserve_cents: Reserve kept for scaling
            distribution_cents: Owner distribution amount
            expected_ev_cents: Expected expected value in cents
            risk_adjusted_ev_cents: Risk-adjusted expected value
            child_id: Child agent ID (if proposal has a child ID)
            proposal_id: Proposal identifier
            source: Emitting component
        """
        payload = {
            "funding_cents": funding_cents,
            "scaling_reserve_cents": scaling_reserve_cents,
            "distribution_cents": distribution_cents,
            "expected_ev_cents": expected_ev_cents,
            "risk_adjusted_ev_cents": risk_adjusted_ev_cents,
        }
        if child_id:
            payload["child_id"] = child_id
        if proposal_id:
            payload["proposal_id"] = proposal_id
        return self.dispatch(EventType.REPRODUCTION_PROPOSED, payload, source)