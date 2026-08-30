#!/usr/bin/env python3
"""DARWIN ZERO-0 Opportunity Model

Models a found opportunity discovered by the Opportunity Analyst.
All amounts in cents. Follows the decision protocol and event model.

Per CONSTITUTION.md and FINANCIAL_POLICY.md:
- No negative-EV allocations without rigorous evidence
- Capital allocation considers EV, risk, liquidity, survivability, etc.
- Opportunities are tracked through the decision protocol lifecycle
"""

from pathlib import Path
import json
import sys
from pathlib import Path

from core.statemanager import append_opportunity, load_state
from events.event_model import EventDispatcher, EventType


class Opportunity:
    """DARWIN ZERO-0 Opportunity Model

    Models a found opportunity discovered by the Opportunity Analyst.
    All amounts in cents. Follows the decision protocol and event model.
    Per CONSTITUTION.md and FINANCIAL_POLICY.md:
    - No negative-EV allocations without rigorous evidence
    - Capital allocation considers EV, risk, liquidity, survivability, etc.
    - Opportunities are tracked through the decision protocol lifecycle
    """

    def __init__(self, description, ev_cents, risk, capital_required_cents, source="opportunity_agent"):
        self.id = f"opp_{hash(description) % 10000:04d}"
        self.description = description
        self.ev_cents = ev_cents
        self.risk = risk
        self.capital_required_cents = capital_required_cents
        self.source = source
        self.status = "discovered"

    def __repr__(self):
        return f"Opportunity(description={self.description!r}, ev_cents={self.ev_cents}, risk={self.risk})"