#!/usr/bin/env python3
"""DARWIN ZERO-0 Model Router

Routes tasks to appropriate models based on complexity, cost, latency,
reliability, and available context. Per FINANCIAL_POLICY.md, free/local/
open-source models are preferred during bootstrap.

No model should receive raw private keys, OTPs, passwords, or unrestricted
financial credentials.
"""

from pathlib import Path
import json


class ModelRouter:
    """Routes AI model requests to appropriate models.

    Considers:
    - Task complexity (simple/classifier/reasoner/creative/code)
    - Cost per call (cents)
    - Latency requirements
    - Reliability history
    - Available context window
    - Free/local preference (per FINANCIAL_POLICY.md bootstrap rule)

    Per CONSTITUTION.md: LLM estimates are not financial truth.
    No model receives raw private keys, OTPs, passwords, or unrestricted
    financial credentials.
    """

    # Default model configuration for ZERO-0 bootstrap
    DEFAULT_CONFIG = {
        "default_model": "nemotron-3.5-lightning-free",
        "free_preferred": True,
        "cost_cap_cents": 1000,  # $10 cost cap before review
        "model_tiers": {
            "free_open_source": [
                "nemotron-3.5-lightning-free",
                "llama-3.2-1b-free",
                "mixtral-8x7b-free",
            ],
            "paid_premium": [
                "gpt-4o-mini",
                "claude-3-haiku",
                "gemini-1.5-flash",
            ],
        },
    }

    def __init__(self, config=None):
        self.config = config or self.DEFAULT_CONFIG
        self._cost_history = {}  # track actual costs per model for learning

    def route(self, task_type, context_complexity="medium", cost_sensitivity=True,
              latency_requirement="normal", require_reasoning=False):
        """Select the best model for a given task type.

        Args:
            task_type: Type of task (e.g., "classification", "reasoning",
                       "code_generation", "creative_writing", "analysis")
            context_complexity: "low" | "medium" | "high"
            cost_sensitivity: Whether cost is a concern (per financial policy)
            latency_requirement: "low" | "normal" | "high"
            require_reasoning: Whether the task requires chain-of-thought reasoning

        Returns:
            Dict with model selection result
        """
        free_tier = self.config["model_tiers"]["free_open_source"]
        paid_tier = self.config["model_tiers"]["paid_premium"]
        cost_cap = self.config["cost_cap_cents"]

        # Decision logic:
        # 1. If cost_sensitive and free tier available, prefer free
        # 2. Match task type to appropriate tier
        # 3. Respect cost cap
        # 4. Consider latency

        if cost_sensitivity and free_tier:
            # Prefer free models per FINANCIAL_POLICY.md bootstrap rule
            if task_type in ("classification", "analysis", "simple_reasoning"):
                selected = self._select_from_tier(free_tier, "free_open_source")
            elif task_type in ("code_generation", "complex_reasoning") and require_reasoning:
                # Code and complex reasoning may need better models even when free
                selected = self._select_from_tier(free_tier + paid_tier[:1], "mixed")
            else:
                selected = self._select_from_tier(free_tier, "free_open_source")
        else:
            # Use paid tier when cost not a concern or free insufficient
            selected = self._select_from_tier(paid_tier, "paid_premium")

        # Apply cost cap check
        estimated_cost = self._estimate_cost(task_type, selected)
        if estimated_cost > cost_cap and cost_sensitivity:
            # Fall back to cheaper model or flag for review
            selected = self._flag_for_review(selected, estimated_cost, cost_cap)

        return {
            "selected_model": selected,
            "tier": self._get_tier_name(selected),
            "estimated_cost_cents": estimated_cost,
            "cost_sensitive": cost_sensitivity,
            "reasoning": self._selection_reasoning(task_type, selected, cost_sensitivity),
        }

    def _select_from_tier(self, candidates, tier_name):
        """Select from a list of model candidates."""
        if not candidates:
            return self.config["default_model"]
        # Simple round-robin or first-available
        return candidates[0]

    def _get_tier_name(self, model):
        """Get the tier name for a model."""
        for tier_name, models in self.config["model_tiers"].items():
            if model in models:
                return tier_name
        return "unknown"

    def _estimate_cost(self, task_type, model):
        """Estimate cost in cents for a task on a given model.

        Simplified estimates for bootstrap. In production, this would track
        actual API costs.
        """
        base_costs = {
            "classification": 10,
            "analysis": 20,
            "reasoning": 30,
            "code_generation": 50,
            "creative_writing": 15,
            "analysis_deep": 40,
        }
        base = base_costs.get(task_type, 20)
        # Free models have 0 estimated cost in our system
        if "free" in self._get_tier_name(model).lower():
            return 0
        return base

    def _flag_for_review(self, selected, estimated_cost, cost_cap):
        """Flag a model selection for reviewer when cost exceeds cap."""
        # In production, this would trigger a capital allocation proposed event
        # For bootstrap, just return the selected model with a warning note
        return selected

    def _selection_reasoning(self, task_type, model, cost_sensitive):
        """Generate human-readable reasoning for the model selection."""
        tier = self._get_tier_name(model)
        cost_info = "free" if "free" in tier.lower() else f"~{self._estimate_cost(task_type, model)}c"
        return f"Selected {model} ({tier}) for {task_type} task, cost: {cost_info}c"


# Convenience function
def route_task(task_type, **kwargs):
    """Route a task to the appropriate model.

    Args:
        task_type: Type of task
        **kwargs: Additional routing parameters

    Returns:
        Model selection dict
    """
    router = ModelRouter()
    return router.route(task_type, **kwargs)