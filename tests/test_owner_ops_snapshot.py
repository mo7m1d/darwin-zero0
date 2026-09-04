import pytest
from owner_ops import OwnerOpsReadModel

def test_snapshot_derived_and_secret_scrubbed():
    readers = {
        "system": lambda: {"state":"RUNNING","safety_version":"3.0.0","api_key":"hidden"},
        "task": lambda: {"name":"CP09.5","progress":"50%"},
        "control": lambda: {"state":"RUNNING","approvals_mode":"manual"},
        "budget": lambda: {"spend":"$0","status":"OK"},
        "model": lambda: {"model":"local","router":"REPO_SIDE_DETERMINISTIC"},
        "recovery": lambda: {"status":"OK"}, "context": lambda: {"status":"OK"},
        "git": lambda: {"commit":"abc","ci":"PASS"}, "security": lambda: {"last_alert":"none"},
    }
    snap = OwnerOpsReadModel(readers, clock=lambda:100).snapshot()
    assert snap["canonical_truth"] is False
    assert snap["sections"]["system"]["api_key"] == "[REDACTED]"

def test_reader_failure_becomes_unknown():
    snap = OwnerOpsReadModel({"system":lambda:(_ for _ in ()).throw(RuntimeError())}).snapshot()
    assert snap["sections"]["system"]["status"] == "UNKNOWN"

def test_shadow_source_rejected():
    with pytest.raises(Exception):
        OwnerOpsReadModel({"shadow_db":lambda:{}})
