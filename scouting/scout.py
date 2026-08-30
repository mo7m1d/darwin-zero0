#!/usr/bin/env python3
"""DARWIN ZERO-0 Technology Scout

Scans for and evaluates capabilities, tools, models, and services against
DARWIN ZERO-0 requirements. Per SELF_IMPROVEMENT_PROTOCOL.md:
- Detect capability gap
- Gather evidence
- Search for skills/tools/APIs/services/models/MCP/libraries
- Compare free/local/open-source/paid options
- Build-vs-buy analysis
- Isolated sandbox trial
- Benchmark quality/cost/speed/reliability/security
- Independent review
- Adopt only if measurably better
- Monitor real-world impact
- Rollback or retire if value degrades

Per FINANCIAL_POLICY.md: prefer zero-cost validation and free/open-source/
local resources during bootstrap.
"""

from pathlib import Path
import json


class TechnologyScout:
    """Scans for and evaluates new capabilities for DARWIN ZERO-0."""

    def __init__(self):
        self.capabilities_file = Path(__file__).parent.parent / "state" / "capabilities.json"
        self.state_path = Path(__file__).parent.parent / "state" / "state.json"

    def scan_capabilities(self, categories=None):
        """Scan for available capabilities in the ecosystem.

        Args:
            categories: List of capability categories to search (e.g., ["models", "tools", "services"])
                       If None, scans all categories.

        Returns:
            List of capability dicts matching the capability schema
        """
        # In a real implementation, this would search PyPI, GitHub, etc.
        # For bootstrap, return a baseline set of free/local capabilities
        baseline = self._baseline_capabilities()

        if categories is None:
            return baseline
        return [c for c in baseline if c.get("category") in categories]

    def _baseline_capabilities(self):
        """Return baseline free/local capabilities available at ZERO-0 bootstrap.

        These are capabilities that require $0 capital outlay and are
        approved per FINANCIAL_POLICY.md.
        """
        return [
            {
                "id": "cap_local_python",
                "name": "Local Python Execution",
                "description": "Python 3.11+ runtime with standard library for local computation, analysis, and automation",
                "cost_cents": 0,
                "source": "system_runtime",
                "status": "available",
                "category": "runtime",
            },
            {
                "id": "cap_local_llm",
                "name": "Local LLM Inference",
                "description": "Nemotron 3.5 Lightning free model via opencode-free provider",
                "cost_cents": 0,
                "source": "opencode-free",
                "status": "available",
                "category": "model",
            },
            {
                "id": "cap_unit_tests",
                "name": "Unit Testing Framework",
                "description": "pytest for Python unit tests and integration tests",
                "cost_cents": 0,
                "source": "pyPI",
                "status": "available",
                "category": "testing",
            },
            {
                "id": "cap_immutable_ledger",
                "name": "Immutable Ledger",
                "description": "Append-only financial ledger with JSON state management",
                "cost_cents": 0,
                "source": "darwin-zero0-core",
                "status": "available",
                "category": "accounting",
            },
            {
                "id": "cap_event_bus",
                "name": "Event Bus / Event Model",
                "description": "Dispatch mechanism for major system events (OPPORTUNITY_FOUND, EXPERIMENT_STARTED, etc.)",
                "cost_cents": 0,
                "source": "darwin-zero0-core",
                "status": "available",
                "category": "infrastructure",
            },
            {
                "id": "cap_self_healing",
                "name": "Self-Healing Loop",
                "description": "11-step protocol for detecting and resolving routine failures",
                "cost_cents": 0,
                "source": "darwin-zero0-core",
                "status": "available",
                "category": "automation",
            },
            {
                "id": "cap_model_router",
                "name": "Model Router",
                "description": "Routes tasks to appropriate models based on cost, latency, and capability",
                "cost_cents": 0,
                "source": "darwin-zero0-core",
                "status": "available",
                "category": "infrastructure",
            },
        ]

    def evaluate_capability(self, capability_id, criteria=None):
        """Evaluate a specific capability against decision criteria.

        Per SELF_IMPROVEMENT_PROTOCOL.md:
        - Compare free/local/open-source/paid options
        - Build-vs-buy analysis
        - Isolated sandbox trial
        - Benchmark quality/cost/speed/reliability/security
        - Independent review
        - Adopt only if measurably better

        Args:
            capability_id: ID of the capability to evaluate
            criteria: Dict of evaluation criteria (quality, cost, speed, reliability, security)

        Returns:
            Evaluation result dict
        """
        if criteria is None:
            criteria = {
                "quality": "medium",
                "cost": "prefer_free",
                "speed": "normal",
                "reliability": "medium",
                "security": "medium",
            }

        # Find the capability
        capabilities = self.scan_capabilities()
        cap = next((c for c in capabilities if c["id"] == capability_id), None)

        if not cap:
            return {"error": f"Capability {capability_id} not found in scan"}

        # Evaluate against criteria
        score = 0
        max_score = 100

        # Cost scoring (higher is better when preferring free)
        if criteria["cost"] == "prefer_free" and cap["cost_cents"] == 0:
            score += 30
        elif criteria["cost"] == "prefer_free":
            # Penalize cost, but don't disqualify
            penalty = min(30, cap["cost_cents"] // 10)
            score = max(0, score - penalty)

        # Quality scoring (simplified)
        if criteria["quality"] == "medium" and cap["status"] == "available":
            score += 25
        elif criteria["quality"] == "high" and cap["status"] == "available":
            score += 10  # Downgrade for not explicitly high-quality

        # Reliability
        if criteria["reliability"] == "medium" and cap["status"] == "available":
            score += 20
        elif criteria["reliability"] == "high" and cap["status"] == "available":
            score += 30

        # Security
        if criteria["security"] == "medium":
            score += 15
        elif criteria["security"] == "high" and cap["cost_cents"] == 0:
            score += 25  # Free/local tends to be more auditable

        # Speed
        if criteria["speed"] == "normal":
            score += 10

        total = min(score, max_score)

        return {
            "capability_id": capability_id,
            "capability_name": cap["name"],
            "scored_against": criteria,
            "total_score": total,
            "max_possible": max_score,
            "recommendation": "adopt" if total >= 60 else "evaluate_further",
            "cost_cents": cap["cost_cents"],
            "category": cap["category"],
        }

    def record_discovered(self, capability_dict):
        """Record a newly discovered capability in state.

        Dispatches CAPABILITY_DISCOVERED event.

        Args:
            capability_dict: Dict matching the capability schema
        """
        from .event_model import EventDispatcher, EventType

        # Ensure cost_cents is set
        if "cost_cents" not in capability_dict:
            capability_dict["cost_cents"] = 0  # Bootstrap default

        # Append to state capabilities
        from .statemanager import append_capability
        append_capability(capability_dict)

        # Dispatch event
        EventDispatcher().capability_discovered(
            name=capability_dict.get("name", "unknown"),
            description=capability_dict.get("description", ""),
            cost_cents=capability_dict["cost_cents"],
            source=capability_dict.get("source", "scout"),
            status=capability_dict.get("status", "available"),
        )

        return capability_dict


# Convenience function
def scout():
    """Initialize a technology scout and return baseline capabilities."""
    return TechnologyScout()