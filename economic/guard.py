from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

from .model import EconomicAmounts, Opportunity, canonical


class GuardDenied(RuntimeError):
    pass


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def valid_hash(value: str) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


@dataclass(frozen=True)
class ScoreLock:
    opportunity_id: str
    amounts: dict
    product_price_cents: int
    supplier_cost_cents: int
    policy_version: str
    policy_hash: str
    fee_schedule_hash: str
    inventory_hash: str
    bug_bounty_scope_hash: str = ""

    @property
    def lock_hash(self) -> str:
        return digest(asdict(self))


@dataclass(frozen=True)
class ExecutionContext:
    product_price_cents: int
    supplier_cost_cents: int
    policy_version: str
    policy_hash: str
    policy_status: str = "CURRENT"
    fee_schedule_hash: str = ""
    inventory_hash: str = ""
    inventory_available: bool = True
    available_quantity: int = 1
    requested_quantity: int = 1
    duplicate_listing: bool = False
    bug_bounty_scope_hash: str = ""
    bug_bounty_authorized: bool = False
    supplier_authorized: bool = True
    supplier_evidence_hash: str = ""
    business_model: str = "ordinary"
    content_rights_verified: bool = True
    trusted_evidence_count: int = 1
    owner_text_claim: str = ""
    retrieved_text: str = ""
    parent_run_id: str = "parent"
    child_parent_ids: tuple[str, ...] = ()
    parent_spend_remaining_cents: int = 0
    child_spend_cents: tuple[int, ...] = ()
    parent_external_effect_limit: int = 0
    child_external_effects: tuple[int, ...] = ()
    consumed_before_restart: int = 0
    consumed_after_restart: int = 0
    retry_count: int = 0
    retry_epoch_before: int = 0
    retry_epoch_after: int = 0
    control_state: str = "RUNNING"
    adapter_registered: bool = True
    adapter_accepted: bool = True
    adapter_self_activation: bool = False
    api_exists: bool = True
    api_permission: bool = False
    endpoint_registered: bool = True
    skill_conflict: bool = False
    canonical_source: str = "accepted_evidence"
    evidence_values: tuple[str, ...] = ()
    paid_fallback_cents: int = 0
    advertising_cents: int = 0
    capital_components_cents: dict[str, int] = field(default_factory=dict)
    pii_fields: tuple[str, ...] = ()
    necessary_pii_fields: tuple[str, ...] = ()
    outreach_recipients: int = 0
    outreach_consent: bool = False
    ordered_units: int = 0
    fulfilled_units: int = 0
    fulfillment_claimed_complete: bool = False
    dry_run: bool = True
    real_write_attempted: bool = False


PROHIBITED_MODELS = {
    "retail_to_ebay_direct_fulfillment", "prohibited_seller_of_record",
    "counterfeit", "trademark_laundering", "copyright_without_rights",
    "fake_review", "fake_identity", "gambling", "alcohol", "cfd", "futures",
    "leverage", "margin_trading", "short_selling",
}
SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|password|access[_-]?token|private[_-]?key|BEGIN [A-Z ]*PRIVATE KEY|\.env(?:\b|/|\\)|otp\b|cookie\b|credential)"
)


class EconomicGuard:
    """Deterministic final gate; text, API existence, and adapters never grant permission."""

    @staticmethod
    def lock(opportunity: Opportunity, context: ExecutionContext) -> ScoreLock:
        return ScoreLock(opportunity.opportunity_id, opportunity.amounts.normalized(),
                         context.product_price_cents, context.supplier_cost_cents,
                         context.policy_version, context.policy_hash,
                         context.fee_schedule_hash, context.inventory_hash,
                         context.bug_bounty_scope_hash)

    @staticmethod
    def violations(opportunity: Opportunity, lock: ScoreLock, context: ExecutionContext) -> list[str]:
        problems: list[str] = []
        current = opportunity.amounts.normalized()
        for name in EconomicAmounts.__dataclass_fields__:
            if current[name] != lock.amounts[name]:
                problems.append(f"scored_{name}_changed")
        if context.product_price_cents != lock.product_price_cents:
            problems.append("product_price_changed")
        if context.supplier_cost_cents != lock.supplier_cost_cents:
            problems.append("supplier_cost_changed")
        if current["expected_profit_cents"] < 0:
            problems.append("negative_margin")
        if context.policy_status != "CURRENT" or context.policy_version != lock.policy_version or context.policy_hash != lock.policy_hash:
            problems.append("marketplace_policy_stale_or_superseded")
        if not valid_hash(context.policy_hash):
            problems.append("policy_provenance_invalid")
        if context.fee_schedule_hash != lock.fee_schedule_hash or not valid_hash(context.fee_schedule_hash):
            problems.append("fee_schedule_stale")
        if context.inventory_hash != lock.inventory_hash or not context.inventory_available:
            problems.append("inventory_stale_or_unavailable")
        if context.requested_quantity < 0 or context.requested_quantity > context.available_quantity or context.duplicate_listing:
            problems.append("oversell_or_duplicate_listing")
        capital_total = sum(context.capital_components_cents.values())
        if capital_total != opportunity.amounts.capital_required_cents:
            problems.append("business_capital_concealed")
        if any(value < 0 for value in context.capital_components_cents.values()):
            problems.append("invalid_capital_component")
        if sum(context.child_spend_cents) > context.parent_spend_remaining_cents:
            problems.append("child_spend_exceeds_parent")
        if sum(context.child_external_effects) > context.parent_external_effect_limit:
            problems.append("child_external_effects_exceed_parent")
        if any(parent != context.parent_run_id for parent in context.child_parent_ids):
            problems.append("child_detached_from_parent")
        if context.consumed_after_restart < context.consumed_before_restart:
            problems.append("restart_or_recovery_counter_rollback")
        if context.retry_count > 3 or context.retry_epoch_after != context.retry_epoch_before:
            problems.append("retry_or_repricing_loop")
        if context.control_state != "RUNNING":
            problems.append("owner_control_not_running")
        if context.owner_text_claim or "disable policy" in context.retrieved_text.casefold() or "owner approved" in context.retrieved_text.casefold():
            problems.append("untrusted_text_authority")
        if not context.supplier_authorized or not valid_hash(context.supplier_evidence_hash):
            problems.append("supplier_authorization_unverified")
        if context.business_model in PROHIBITED_MODELS:
            problems.append("prohibited_business_model")
        if context.business_model == "authorized_bug_bounty":
            if not context.bug_bounty_authorized or context.bug_bounty_scope_hash != lock.bug_bounty_scope_hash:
                problems.append("bug_bounty_unauthorized_or_scope_changed")
        if context.business_model in {"counterfeit", "trademark_laundering", "copyright_without_rights"} or not context.content_rights_verified:
            problems.append("intellectual_property_rights_missing")
        if context.outreach_recipients > 1 and not context.outreach_consent:
            problems.append("spam_outreach")
        if set(context.pii_fields) - set(context.necessary_pii_fields):
            problems.append("unnecessary_pii")
        maximum_confidence = min(10_000, context.trusted_evidence_count * 2_000)
        if opportunity.amounts.evidence_confidence_bps > maximum_confidence:
            problems.append("confidence_not_supported_by_evidence")
        if context.paid_fallback_cents > 0 or context.advertising_cents > opportunity.amounts.capital_required_cents:
            problems.append("hidden_paid_fallback_or_ad_spend")
        if context.adapter_self_activation or not context.adapter_registered or not context.adapter_accepted:
            problems.append("adapter_not_accepted")
        if context.api_exists and not context.api_permission:
            problems.append("api_existence_is_not_permission")
        if not context.endpoint_registered:
            problems.append("hallucinated_api_endpoint")
        if context.skill_conflict:
            problems.append("skill_conflict")
        if context.canonical_source != "accepted_evidence":
            problems.append("shadow_database_not_authoritative")
        if any(SECRET_PATTERN.search(value) for value in context.evidence_values):
            problems.append("secret_like_evidence_rejected")
        if context.fulfillment_claimed_complete and context.fulfilled_units != context.ordered_units:
            problems.append("partial_or_fake_fulfillment")
        if context.dry_run and context.real_write_attempted:
            problems.append("dry_run_real_write")
        return sorted(set(problems))

    @classmethod
    def require_safe(cls, opportunity: Opportunity, lock: ScoreLock, context: ExecutionContext) -> None:
        problems = cls.violations(opportunity, lock, context)
        if problems:
            raise GuardDenied(";".join(problems))
