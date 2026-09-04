from owner_ops import OwnerOpsReadModel
from run_control.budget_store import BudgetStore
from continuity.engine import ContinuityEngine
from model_control import Router

def test_cp11_cp12_cp13_import_and_read_foundation(tmp_path):
    store=BudgetStore(tmp_path/"b.db",clock=lambda:100)
    assert store.verify_ledger()
    engine=ContinuityEngine(tmp_path/"c.db")
    assert engine.retrieve("nothing")["bounded"] is True
    assert Router is not None
    snap=OwnerOpsReadModel({
        "budget":lambda:{"status":"OK","spend":"$0"},
        "context":lambda:{"status":"OK","mode":"DETERMINISTIC_LOCAL"},
        "model":lambda:{"router":"REPO_SIDE_DETERMINISTIC","cost_boundary":"LIMITED"},
    },clock=lambda:1).snapshot()
    assert snap["sections"]["budget"]["spend"]=="$0"
