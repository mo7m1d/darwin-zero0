import tempfile
from pathlib import Path

from economic import (EconomicAmounts, EconomicEngine, EconomicStore, Opportunity,
                      OpportunityState, default_capability_registry)


with tempfile.TemporaryDirectory(prefix="eco00-drill-") as temporary:
    database = Path(temporary) / "economic.sqlite3"
    first = EconomicEngine(default_capability_registry(), EconomicStore(database, now=lambda: 100))
    first.add(Opportunity("dry-run", "software_delivery", "Dry-run service",
                          EconomicAmounts(10_000, payment_fees_cents=300,
                                          expected_hours_milli=2000, uncertainty_bps=500,
                                          evidence_confidence_bps=9000)))
    for state in (OpportunityState.RESEARCHED, OpportunityState.POLICY_CHECKED,
                  OpportunityState.SCORED, OpportunityState.CANDIDATE,
                  OpportunityState.DRY_RUN_READY):
        first.transition("dry-run", state, actor="reviewer", evidence_ref=f"fixture://{state.value}")
    restarted = EconomicEngine(default_capability_registry(), EconomicStore(database, now=lambda: 200))
    item = restarted.store.get("dry-run")
    assert item.state == OpportunityState.DRY_RUN_READY
    assert item.amounts.expected_profit_cents == 9700
    assert restarted.store.verify_ledger()
    assert item.amounts.capital_required_cents == 0

print("ECO00_ISOLATED_RESTART_DRY_RUN=PASS")
print("OWNER_SUPPLIED_BUSINESS_CAPITAL_CENTS=0")
print("PAID_CALLS=0")
print("REAL_MARKETPLACE_WRITES=0")
