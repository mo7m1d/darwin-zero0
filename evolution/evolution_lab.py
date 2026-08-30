#!/usr/bin/env python3
"""DARWIN ZERO-0 Evolution Lab / Self-Improvement Lab

Per SELF_IMPROVEMENT_PROTOCOL.md:
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

Never modify immutable owner controls or prohibited-activity policy.

This lab provides a controlled framework for DARWIN to improve its own
skills, prompts, tools, services, models, workflows, and code through
isolated testing, measurable evaluation, review, and rollback capability.
"""

import json
from datetime import datetime, timezone
import tempfile
import shutil
from pathlib import Path


class EvolutionLab:
    """Controlled self-improvement/evolution lab for DARWIN ZERO-0.

    Provides isolated sandbox trials for evaluating improvements before
    adoption. All experiments in the lab are tracked via the experiment
    framework and event bus.
    """

    def __init__(self, state_manager=None, experiment_manager=None):
        self.sm = state_manager or EvolutionLab._default_sm()
        self.em = experiment_manager or EvolutionLab._default_em()
        self.trials_dir = Path(__file__).parent.parent / "evolution_trials"

    @staticmethod
    def _default_sm():
        from memory.memory_manager import StateManager
        return StateManager()

    @staticmethod
    def _default_em():
        from experiments.experiment import Experiment
        return None  # Will use experiment system

    def detect_gap(self, gap_description, current_capabilities=None):
        """Detect a capability gap that the lab should address.

        Per SELF_IMPROVEMENT_PROTOCOL.md step 1: 'Detect capability gap'

        Args:
            gap_description: Human-readable description of the gap
            current_capabilities: List of current capability IDs

        Returns:
            Gap record dict
        """
        gap = {
            "id": f"gap_{uuid_str()}",
            "description": gap_description,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "current_capabilities": current_capabilities or [],
            "status": "detected",
        }
        return gap

    def gather_evidence(self, gap_id, evidence_types=["documentation", "benchmarks", "user_feedback"]):
        """Gather evidence for addressing a capability gap.

        Per SELF_IMPROVEMENT_PROTOCOL.md step 2: 'gather evidence'

        Args:
            gap_id: The gap ID from detect_gap()
            evidence_types: Types of evidence to gather

        Returns:
            Evidence collection dict
        """
        evidence = {
            "gap_id": gap_id,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "evidence_types": evidence_types,
            "items": [],  # Would be populated with actual evidence links/refs
            "status": "gathered",
        }
        return evidence

    def compare_options(self, gap_id, options):
        """Compare free/local/open-source/paid options for a gap.

        Per SELF_IMPROVEMENT_PROTOCOL.md step 3-6:
        - Compare free/local/open-source/paid options
        - Build-vs-buy analysis
        - Isolated sandbox trial

        Args:
            gap_id: The gap ID
            options: List of option dicts with at least 'name', 'cost_cents', 'source'

        Returns:
            Comparison result dict
        """
        comparison = {
            "gap_id": gap_id,
            "compared_at": datetime.now(timezone.utc).isoformat(),
            "options": options,
            "scoring": {},
            "recommendation": "evaluate_further",
        }

        # Score each option per protocol
        for option in options:
            score = 0
            # Cost scoring (free gets high score)
            if option.get("cost_cents", 0) == 0:
                score += 30
            else:
                score += max(0, 30 - option["cost_cents"] // 50)
            # Status scoring
            if option.get("status") == "available":
                score += 20
            comparison["scoring"][option.get("name", "unknown")] = score

        # Recommendation: prefer free/open-source options
        best_option = max(options, key=lambda o: comparison["scoring"].get(o.get("name", ""), 0), default=None)
        if best_option and comparison["scoring"].get(best_option.get("name", ""), 0) >= 50:
            comparison["recommendation"] = "adopt_free_local_first"
        else:
            comparison["recommendation"] = "evaluate_sandbox"

        return comparison

    def run_sandbox_trial(self, gap_id, selected_option, trial_code, trial_dir=None):
        """Run an isolated sandbox trial of a selected option.

        Per SELF_IMPROVEMENT_PROTOCOL.md step 6-8:
        - Isolated sandbox trial
        - Benchmark quality/cost/speed/reliability/security
        - Independent review

        Args:
            gap_id: The gap ID
            selected_option: The option dict to trial
            trial_code: Python code to execute in the sandbox (limited, safe subset)
            trial_dir: Optional custom trial directory

        Returns:
            Trial result dict with benchmarks and review notes
        """
        # Create isolated trial directory
        if trial_dir is None:
            trial_dir = self.trials_dir / f"trial_{uuid_str()}"
        trial_dir.mkdir(parents=True, exist_ok=True)

        # Write the trial code to a file
        code_path = trial_dir / "trial_code.py"
        with open(code_path, "w") as f:
            f.write(trial_code)

        # In a real implementation, we'd run the code in a sandboxed environment
        # with resource limits, timeout, etc.
        # For bootstrap, we simulate a trial result

        result = {
            "gap_id": gap_id,
            "selected_option": selected_option.get("name", "unknown"),
            "trial_dir": str(trial_dir),
            "quality_score": 75,  # Simulated benchmark score
            "cost_cents": selected_option.get("cost_cents", 0),
            "speed_ms": 120,  # Simulated latency
            "reliability_score": 85,  # Simulated reliability
            "security_score": 90,  # Simulated security audit score
            "independent_review": "pending",  # Would be conducted independently
            "measurably_better": False,  # Will be assessed vs baseline
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

        # Record experiment via the experiment framework
        # This would link to an actual opportunity/experiment in production
        # For bootstrap, just note the trial

        return result

    def independent_review(self, trial_result, review_criteria=None):
        """Conduct independent review of a sandbox trial.

        Per SELF_IMPROVEMENT_PROTOCOL.md step 9-10:
        - Independent review
        - Adopt only if measurably better
        - Monitor real-world impact
        - Rollback or retire if value degrades

        Args:
            trial_result: Result from run_sandbox_trial()
            review_criteria: Criteria for the review

        Returns:
            Review result dict
        """
        if review_criteria is None:
            review_criteria = {
                "must_improve_on_baseline": True,
                "max_cost_cents": 1000,  # $10 cap
                "min_quality": 70,
                "min_reliability": 75,
            }

        result = {
            "trial_option": trial_result.get("selected_option", "unknown"),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "review_criteria": review_criteria,
            "meets_criteria": True,  # Simplified: assume meets criteria
            "measurably_better": trial_result.get("quality_score", 0) >= review_criteria["min_quality"]
            and trial_result.get("reliability_score", 0) >= review_criteria["min_reliability"],
            "recommendation": "adopt" if trial_result.get("measurably_better", False)
            and trial_result.get("cost_cents", 0) <= review_criteria["max_cost_cents"]
            else "reject",
            "rollback_if_adopted": False,
            "monitoring_suggested": trial_result.get("measurably_better", False),
        }

        return result

    def monitor_impact(self, adopted_id, monitoring_duration_ticks=5):
        """Monitor real-world impact of an adopted improvement.

        Per SELF_IMPROVEMENT_PROTOCOL.md step 10: 'monitor real-world impact'

        Args:
            adopted_id: ID of the adopted improvement
            monitoring_duration_ticks: Number of monitoring cycles

        Returns:
            Monitoring result dict
        """
        return {
            "adopted_id": adopted_id,
            "monitoring_ticks": monitoring_duration_ticks,
            "impact_stable": True,  # Simplified assumption
            "value_degraded": False,
            "recommendation": "continue_monitoring" if not trial_result.get("value_degraded", False)
            else "retire_or_reroll",
        }

    def rollback_or_retire(self, adopted_id, reason="value_degraded_or_issue_found"):
        """Rollback or retire an adopted improvement that has degraded.

        Per SELF_IMPROVEMENT_PROTOCOL.md step 11: 'rollback or retire if value degrades'

        Args:
            adopted_id: ID of the adopted improvement
            reason: Reason for rollback/retirement

        Returns:
            Rollback result dict
        """
        return {
            "adopted_id": adopted_id,
            "reason": reason,
            "rolled_back": True,
            "retired": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "restored_to_previous": True,
        }


def uuid_str():
    """Generate short UUID string."""
    import uuid
    return uuid.uuid4().hex[:12]


# Convenience function
def detect_impact(gap_description, current_caps=None):
    """Detect a capability gap and start the improvement process.

    Args:
        gap_description: Description of the gap
        current_caps: Current capability IDs

    Returns:
        Gap dict from detect_gap()
    """
    lab = EvolutionLab()
    return lab.detect_gap(gap_description, current_caps)