from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum

MAX_INT = 2**63 - 1
BPS = 10_000


class EconomicValueError(ValueError):
    pass


def integer(value, name: str, maximum: int = MAX_INT) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > maximum:
        raise EconomicValueError(f"invalid {name}")
    return value


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class OpportunityState(str, Enum):
    DISCOVERED = "DISCOVERED"
    RESEARCHED = "RESEARCHED"
    POLICY_CHECKED = "POLICY_CHECKED"
    SCORED = "SCORED"
    CANDIDATE = "CANDIDATE"
    OWNER_DECISION = "OWNER_DECISION"
    DRY_RUN_READY = "DRY_RUN_READY"
    EXECUTION_READY = "EXECUTION_READY"
    EXECUTING = "EXECUTING"
    ACCEPTANCE_PENDING = "ACCEPTANCE_PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class EconomicAmounts:
    expected_revenue_cents: int
    marketplace_fees_cents: int = 0
    payment_fees_cents: int = 0
    fulfillment_cents: int = 0
    acquisition_cents: int = 0
    tax_reserve_cents: int = 0
    expected_refund_loss_cents: int = 0
    capital_required_cents: int = 0
    expected_hours_milli: int = 0
    uncertainty_bps: int = 0
    policy_risk_bps: int = 0
    execution_risk_bps: int = 0
    evidence_confidence_bps: int = BPS

    def __post_init__(self):
        for name, value in asdict(self).items():
            integer(value, name, BPS if name.endswith("_bps") else MAX_INT)
        if self.expected_cost_cents > MAX_INT:
            raise EconomicValueError("expected cost overflow")

    @property
    def expected_cost_cents(self) -> int:
        return sum((self.marketplace_fees_cents, self.payment_fees_cents,
                    self.fulfillment_cents, self.acquisition_cents,
                    self.tax_reserve_cents, self.expected_refund_loss_cents))

    @property
    def expected_profit_cents(self) -> int:
        return self.expected_revenue_cents - self.expected_cost_cents

    @property
    def margin_bps(self) -> int:
        return 0 if self.expected_revenue_cents == 0 else self.expected_profit_cents * BPS // self.expected_revenue_cents

    @property
    def risk_adjusted_profit_cents(self) -> int:
        profit = self.expected_profit_cents
        if profit <= 0:
            return profit
        combined_risk = min(BPS, self.uncertainty_bps + self.policy_risk_bps + self.execution_risk_bps)
        return profit * (BPS - combined_risk) * self.evidence_confidence_bps // (BPS * BPS)

    def normalized(self) -> dict:
        value = asdict(self)
        value.update(expected_cost_cents=self.expected_cost_cents,
                     expected_profit_cents=self.expected_profit_cents,
                     margin_bps=self.margin_bps,
                     risk_adjusted_profit_cents=self.risk_adjusted_profit_cents)
        return value


@dataclass(frozen=True)
class Opportunity:
    opportunity_id: str
    family_id: str
    title: str
    amounts: EconomicAmounts
    state: OpportunityState = OpportunityState.DISCOVERED
    platform_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    policy_passed: bool = False
    dry_run_passed: bool = False
    owner_capital_authorized: bool = False
    capital_components_cents: dict[str, int] = field(default_factory=dict)
    schema_version: str = "darwin.eco00.opportunity.v1"

    def __post_init__(self):
        if not self.opportunity_id or not self.family_id or not self.title.strip():
            raise EconomicValueError("opportunity identity required")
        permitted = {"purchase", "acquisition", "deposit", "fulfillment", "inventory", "other"}
        if set(self.capital_components_cents) - permitted:
            raise EconomicValueError("unknown capital component")
        for name, value in self.capital_components_cents.items():
            integer(value, f"capital component {name}")
        declared = sum(self.capital_components_cents.values())
        if declared > MAX_INT or declared != self.amounts.capital_required_cents:
            raise EconomicValueError("capital components must equal capital_required_cents")

    def payload(self) -> dict:
        result = asdict(self)
        result["state"] = self.state.value
        result["amounts"] = self.amounts.normalized()
        result["evidence_refs"] = list(self.evidence_refs)
        return result

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(canonical(self.payload()).encode()).hexdigest()

    @property
    def rank_key(self) -> tuple:
        a = self.amounts
        return (-a.risk_adjusted_profit_cents, -a.expected_profit_cents, -a.margin_bps,
                a.capital_required_cents, a.expected_hours_milli, self.opportunity_id)
