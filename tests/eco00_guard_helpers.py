from dataclasses import replace

from economic import EconomicAmounts, EconomicGuard, ExecutionContext, Opportunity


def opportunity(**amount_changes):
    values = dict(expected_revenue_cents=10_000, marketplace_fees_cents=500,
                  payment_fees_cents=300, fulfillment_cents=1_000,
                  acquisition_cents=200, tax_reserve_cents=800,
                  expected_refund_loss_cents=200, capital_required_cents=0,
                  expected_hours_milli=2_000, uncertainty_bps=500,
                  policy_risk_bps=500, execution_risk_bps=500,
                  evidence_confidence_bps=10_000)
    values.update(amount_changes)
    return Opportunity("guarded", "software_delivery", "Guarded", EconomicAmounts(**values))


def context(**changes):
    values = dict(product_price_cents=10_000, supplier_cost_cents=200,
                  policy_version="policy-v1", policy_hash="a" * 64,
                  fee_schedule_hash="b" * 64, inventory_hash="c" * 64,
                  supplier_evidence_hash="d" * 64, trusted_evidence_count=5,
                  api_permission=True, parent_spend_remaining_cents=0,
                  parent_external_effect_limit=0, ordered_units=1, fulfilled_units=1)
    values.update(changes)
    return ExecutionContext(**values)


def locked(item=None, state=None):
    item = item or opportunity()
    state = state or context()
    return EconomicGuard.lock(item, state)


def changed_amount(item, **changes):
    return replace(item, amounts=replace(item.amounts, **changes))
