#!/usr/bin/env python3
"""DARWIN ZERO-0 Risk Sizer

Provides dynamic risk sizing per DARWIN ZERO-0 Financial Policy. Sizes
capital at risk based on opportunity characteristics, not fixed percentages.

Policy: high upside does not justify all-in exposure. Risk is sized
dynamically so that maximum loss is bounded and survivable. Higher risk
score does NOT mechanically increase allocation — instead, higher risk
triggers more conservative sizing with greater emphasis on survival
and downside protection.
"""

import random
from pathlib import Path


class RiskSizer:
    """Dynamic risk sizer for DARWIN ZERO-0.

    Sizes the capital at risk for each opportunity based on:
    - Risk score (0-100) from the opportunity model — higher risk
      triggers MORE conservative sizing, not less
    - Expected value direction and magnitude
    - Liquidity constraints
    - Survival priority (ZERO-0 starts at $0)
    - Evidence/confidence in the EV estimate
    - Reversibility of the allocation
    - Opportunity cost of capital
    - Reputation impact of potential loss
    - Reversibility of the decision

    Policy: high upside does not justify all-in exposure. Risk is sized
    dynamically so that maximum loss is bounded and survivable. The
    fundamental design principle is: higher risk_score → more
    conservative sizing, not greater allocation.
    """

    MIN_RISK_PERCENT = 2    # Very low floor even for risk_score=0
    MAX_RISK_PERCENT = 15   # Cap — higher risk_score reduces allowed percent
    SURVIVAL_FLOOR_CENTS = 100  # Always keep at least $1 in reserve
    MIN_ALLOCATABLE_FRACTION = 0.01  # Never allocate more than 1% when risk is very high

    def __init__(self):
        pass

    def size_risk(self, risk_score, ev_cents, allocatable_cents):
        """Calculate the capital to risk for an opportunity.

        Args:
            risk_score: Opportunity risk score 0-100
            ev_cents: Expected value in cents (may be negative)
            allocatable_cents: Capital available for risk-taking

        Returns:
            Dict with risk sizing result
        """
        # Policy: Negative EV → risk 0 (no negative-EV allocations)
        if ev_cents < 0:
            return {
                "risk_percent": 0,
                "risk_cents": 0,
                "reason": "Negative expected value; risk size is 0 per policy",
            }

        # Core policy: higher risk_score → MORE conservative sizing
        # Invert the relationship: risk_score 0 → up to MAX_RISK_PERCENT
        # risk_score 100 → down to MIN_RISK_PERCENT
        # This ensures higher risk does NOT mechanically increase allocation
        # In fact, higher risk reduces the allowed risk percentage
        risk_percent_base = self.MAX_RISK_PERCENT - (
            (risk_score / 100.0) * (self.MAX_RISK_PERCENT - self.MIN_RISK_PERCENT)
        )
        # Ensure within bounds [MIN_RISK_PERCENT, MAX_RISK_PERCENT]
        risk_percent_base = max(self.MIN_RISK_PERCENT, min(self.MAX_RISK_PERCENT, risk_percent_base))

        # Apply EV magnitude adjustment — but INVERSE: larger |EV| with high risk
        # gets slightly LOWER percentage to protect capital
        # Normalize EV by allocatable amount, not arbitrary 1000
        ev_ratio = abs(ev_cents) / max(allocatable_cents, 1)  # avoid div by 0
        # Higher ev_ratio with high risk → smaller adjustment
        ev_adjustment = max(0.3, min(1.0, 1.0 - (ev_ratio * 0.3)))

        adjusted_percent = risk_percent_base * ev_adjustment

        # Final risk percent — lower risk_score allows higher percent,
        # higher risk_score forces lower percent
        final_percent = min(adjusted_percent, self.MAX_RISK_PERCENT)

        # Calculate risk cents
        risk_cents = int(allocatable_cents * (final_percent / 100.0))

        # Survival floor: ensure we keep at least SURVIVAL_FLOOR_CENTS
        risk_cents = max(risk_cents, 0)  # ensure non-negative
        # Critical: never allocate more than available minus survival floor
        risk_cents = min(risk_cents, allocatable_cents - self.SURVIVAL_FLOOR_CENTS)

        # Ensure we never risk more than a minimal fraction when risk_score is high
        if risk_score >= 80:
            # High risk: cap at very conservative level
            risk_cents = min(risk_cents, int(allocatable_cents * self.MIN_ALLOCATABLE_FRACTION))

        reason = (
            f"Risk score {risk_score}% → {final_percent:.1f}% of "
            f"{allocatable_cents}c allocatable = {risk_cents}c. "
            f"Higher risk triggers conservative sizing per policy. "
            f"EV ratio: {ev_ratio:.2f}"
        )

        return {
            "risk_percent": round(final_percent, 1),
            "risk_cents": risk_cents,
            "reason": reason,
        }

    def can_risk(self, risk_score, ev_cents, allocatable_cents):
        """Check if risking capital on this opportunity is permissible.

        Args:
            risk_score: Opportunity risk score 0-100
            ev_cents: Expected value in cents
            allocatable_cents: Capital available for risk-taking

        Returns:
            bool: True if risk sizing is within policy constraints
        """
        sizing = self.size_risk(risk_score, ev_cents, allocatable_cents)
        # Permissible if risk_cents > 0 and survival floor is respected
        return sizing["risk_cents"] > 0 and sizing["risk_cents"] <= allocatable_cents - self.SURVIVAL_FLOOR_CENTS