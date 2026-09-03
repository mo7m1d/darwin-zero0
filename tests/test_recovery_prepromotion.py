from __future__ import annotations

import hashlib
import json
from pathlib import Path

from recovery.runtime_integration import IntegratedRecoveryManager, StrictRecoveryKnowledge, build_candidate_profile, file_sha256, validate_profile


def profile(tmp_path: Path):
    state = tmp_path / "state"
    registry = tmp_path / "integration_registry.json"
    registry.write_text("{}\n", encoding="utf-8")
    p = build_candidate_profile(
        state_root=state,
        checkpoint_root=tmp_path / "candidate-checkpoints",
        live_hermes_home=tmp_path / "live-hermes",
        canonical_head="a" * 64,
        hermes_head="b" * 64,
        plugin_versions={"darwin-tool-policy": "2.6.0"},
        approvals_mode="manual",
        integration_registry_ref=str(registry),
        integration_registry_sha256=file_sha256(registry),
    )
    return state, p


def put(p, root_id, data=b"{}\n"):
    entry = next(x for x in p["entries"] if x["id"] == root_id)
    path = Path(entry["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_profile_is_exact_and_git_backed(tmp_path):
    _, p = profile(tmp_path)
    assert validate_profile(p)
    assert p["source_recovery"] == "git_only"
    assert len(p["entries"]) == 9


def test_provenance_is_safe_and_complete(tmp_path):
    _, p = profile(tmp_path)
    provenance = p["provenance"]
    assert provenance["safe_config_flags"] == {"approvals.mode": "manual"}
    assert len(provenance["integration_registry"]["sha256"]) == 64
    assert "secret" not in json.dumps(provenance).casefold()


def test_isolated_create_verify_restore_drill(tmp_path):
    _, p = profile(tmp_path)
    target = put(p, "kanban_board_metadata", b'{"value":"before"}\n')
    manager = IntegratedRecoveryManager(p)
    before = file_sha256(target)
    manager.create_checkpoint("drill", ["kanban_board_metadata"], ["test:drill"])
    target.write_bytes(b'{"value":"after"}\n')
    current = file_sha256(target)
    manager.restore_checkpoint("drill", expected_current_hashes={"kanban_board_metadata:board.json": current}, owner_authorized=True)
    assert file_sha256(target) == before


def test_archive_ledgers_cannot_reset_history(tmp_path):
    _, p = profile(tmp_path)
    target = put(p, "control_supervisor", b"ledger")
    manager = IntegratedRecoveryManager(p)
    manager.create_checkpoint("audit", ["control_supervisor"], ["test:audit"])
    try:
        manager.restore_checkpoint("audit", expected_current_hashes={"control_supervisor:decisions.sqlite3": file_sha256(target)}, owner_authorized=True)
    except Exception as exc:
        assert "archive-only" in str(exc)
    else:
        raise AssertionError("archive-only ledger was restorable")


def test_verified_acceptance_can_promote_data_only_knowledge(tmp_path):
    acceptance = tmp_path / "acceptance"
    acceptance.mkdir()
    receipt = acceptance / "receipt.json"
    receipt.write_text(json.dumps({"schema": "darwin.acceptance.receipt.v1", "verdict": "PASS", "acceptance_ref": "acceptance:test"}) + "\n", encoding="utf-8")
    knowledge = StrictRecoveryKnowledge(tmp_path / "knowledge.json", acceptance)
    knowledge.add_candidate(knowledge_id="k1", incident_signature="sig", action_kind="investigate_only", recovery_summary="Inspect verified local evidence.", provenance="runtime:test", evidence_refs=["test:k1"])
    promoted = knowledge.promote_with_verified_acceptance("k1", receipt_path=receipt, expected_sha256=file_sha256(receipt), acceptance_ref="acceptance:test")
    assert promoted["trusted_for_auto_use"] is True


def test_profile_contains_no_live_checkpoint_creation(tmp_path):
    _, p = profile(tmp_path)
    assert "candidate-checkpoints" in p["checkpoint_root"]
    assert not Path(p["live_recovery_root"]).exists()
