#!/usr/bin/env python3
"""DARWIN ZERO-0 Experiment Model

Models an experiment triggered by an opportunity.
Per the decision protocol and self-healing/improvement protocols.
All amounts in cents. Experiments have a lifecycle and produce learnings
that feed back into the opportunity/decision pipeline.
"""

from pathlib import Path
import json
import sys
from pathlib import Path

from core.statemanager import append_experiment, load_state
from events.event_model import EventDispatcher, EventType


class Experiment:
    """DARWIN ZERO-0 Experiment Model

    Models an experiment triggered by an opportunity.
    Per the decision protocol and self-healing/improvement protocols.
    All amounts in cents. Experiments have a lifecycle and produce learnings
that feed back into the opportunity/decision pipeline.
    """

    def __init__(self, opportunity_id, hypothesis, method, cost_cents, source="experiment orchestrator"):
        self.id = f"exp_{hash(opportunity_id) % 10000:04d}"
        self.opportunity_id = opportunity_id
        self.hypothesis = hypothesis
        self.method = method
        self.cost_cents = cost_cents
        self.source = source
        self.status = "pending"

    def __repr__(self):
        return f"Experiment(id={self.id!r}, hypothesis={self.hypothesis!r}, status={self.status!r})"