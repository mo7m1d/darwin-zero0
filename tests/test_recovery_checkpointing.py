from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from recovery.checkpoint_manager import CheckpointError, CheckpointManager
from recovery.recovery_knowledge import RecoveryKnowledgeError, RecoveryKnowledgeStore


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def runtime(tmp_path):
    state = tmp_path / "runtime"
    state.mkdir()
    (state / "state.json").write_text('{"version":1,"value":"before"}\n', encoding="utf-8")
    (state / "incidents.json").write_text("[]\n", encoding="utf-8")
    manager = CheckpointManager(
        tmp_path / "checkpoints",
        {"runtime": state},
        max_file_bytes=1024 * 1024,
    )
    return tmp_path, state, manager


def test_create_verify_restore_round_trip(runtime):
    _, state, manager = runtime
    source = state / "state.json"
    before = digest(source)
    manager.create_checkpoint(
        "cp-001",
        [source],
        provenance="test-runtime",
        evidence_refs=["test:round-trip"],
    )
    source.write_text('{"version":1,"value":"after"}\n', encoding="utf-8")
    changed = digest(source)
    plan = manager.plan_restore(
        "cp-001",
        expected_current_hashes={"runtime:state.json": changed},
    )
    assert len(plan) == 1
    manager.restore_checkpoint(
        "cp-001",
        expected_current_hashes={"runtime:state.json": changed},
        owner_authorized=True,
    )
    assert digest(source) == before


def test_restore_requires_owner_authorization(runtime):
    _, state, manager = runtime
    source = state / "state.json"
    manager.create_checkpoint(
        "cp-001",
        [source],
        provenance="test-runtime",
        evidence_refs=["test:owner-auth"],
    )
    with pytest.raises(CheckpointError, match="owner authorization"):
        manager.restore_checkpoint(
            "cp-001",
            expected_current_hashes={"runtime:state.json": digest(source)},
            owner_authorized=False,
        )


def test_restore_stale_write_guard(runtime):
    _, state, manager = runtime
    source = state / "state.json"
    manager.create_checkpoint(
        "cp-001",
        [source],
        provenance="test-runtime",
        evidence_refs=["test:stale-write"],
    )
    expected = digest(source)
    source.write_text('{"version":1,"value":"newer"}\n', encoding="utf-8")
    with pytest.raises(CheckpointError, match="stale-write guard"):
        manager.plan_restore(
            "cp-001",
            expected_current_hashes={"runtime:state.json": expected},
        )


def test_secretish_path_blocked(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    secret = runtime / ".env"
    secret.write_text("SECRET=not-read\n", encoding="utf-8")
    manager = CheckpointManager(tmp_path / "checkpoints", {"runtime": runtime})
    with pytest.raises(CheckpointError, match="secret-like"):
        manager.create_checkpoint(
            "cp-001",
            [secret],
            provenance="test",
            evidence_refs=["test:secret"],
        )


def test_outside_root_blocked(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    manager = CheckpointManager(tmp_path / "checkpoints", {"runtime": runtime})
    with pytest.raises(CheckpointError, match="outside"):
        manager.create_checkpoint(
            "cp-001",
            [outside],
            provenance="test",
            evidence_refs=["test:outside"],
        )


def test_oversized_file_blocked(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "state.bin"
    source.write_bytes(b"x" * 33)
    manager = CheckpointManager(
        tmp_path / "checkpoints",
        {"runtime": runtime},
        max_file_bytes=32,
    )
    with pytest.raises(CheckpointError, match="size cap"):
        manager.create_checkpoint(
            "cp-001",
            [source],
            provenance="test",
            evidence_refs=["test:size"],
        )


def test_duplicate_checkpoint_blocked(runtime):
    _, state, manager = runtime
    source = state / "state.json"
    manager.create_checkpoint(
        "cp-001",
        [source],
        provenance="test",
        evidence_refs=["test:dup"],
    )
    with pytest.raises(CheckpointError, match="already exists"):
        manager.create_checkpoint(
            "cp-001",
            [source],
            provenance="test",
            evidence_refs=["test:dup2"],
        )


def test_manifest_tamper_detected(runtime):
    tmp, state, manager = runtime
    source = state / "state.json"
    manager.create_checkpoint(
        "cp-001",
        [source],
        provenance="test",
        evidence_refs=["test:manifest"],
    )
    manifest = tmp / "checkpoints" / "cp-001" / "manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    with pytest.raises(CheckpointError, match="manifest hash mismatch"):
        manager.verify_checkpoint("cp-001")


def test_payload_tamper_detected(runtime):
    tmp, state, manager = runtime
    manager.create_checkpoint(
        "cp-001",
        [state / "state.json"],
        provenance="test",
        evidence_refs=["test:payload"],
    )
    payload = tmp / "checkpoints" / "cp-001" / "payload" / "runtime" / "state.json"
    payload.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(CheckpointError, match="payload"):
        manager.verify_checkpoint("cp-001")


def test_extra_payload_detected(runtime):
    tmp, state, manager = runtime
    manager.create_checkpoint(
        "cp-001",
        [state / "state.json"],
        provenance="test",
        evidence_refs=["test:surface"],
    )
    extra = tmp / "checkpoints" / "cp-001" / "payload" / "runtime" / "extra.json"
    extra.write_text("{}\n", encoding="utf-8")
    with pytest.raises(CheckpointError, match="surface mismatch"):
        manager.verify_checkpoint("cp-001")


def test_ledger_tamper_detected(runtime):
    tmp, state, manager = runtime
    manager.create_checkpoint(
        "cp-001",
        [state / "state.json"],
        provenance="test",
        evidence_refs=["test:ledger"],
    )
    ledger = tmp / "checkpoints" / "checkpoint-ledger.jsonl"
    record = json.loads(ledger.read_text(encoding="utf-8"))
    record["checkpoint_id"] = "poisoned"
    ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(CheckpointError, match="record hash mismatch"):
        manager.verify_ledger()


def test_recovery_knowledge_requires_acceptance(tmp_path):
    store = RecoveryKnowledgeStore(tmp_path / "knowledge.json")
    store.add_candidate(
        knowledge_id="rk-1",
        incident_signature="sig:1",
        action_kind="minimal_patch",
        recovery_summary="Use the previously accepted minimal patch.",
        provenance="runtime:test",
        evidence_refs=["test:rk"],
    )
    assert store.recommend("sig:1") == []
    with pytest.raises(RecoveryKnowledgeError, match="PASS"):
        store.promote_with_acceptance(
            "rk-1",
            acceptance_ref="acceptance:bad",
            acceptance_verdict="FAIL",
        )
    promoted = store.promote_with_acceptance(
        "rk-1",
        acceptance_ref="acceptance:gate-123",
        acceptance_verdict="PASS",
    )
    assert promoted["trusted_for_auto_use"] is True
    assert len(store.recommend("sig:1")) == 1


def test_non_acceptance_reviewer_cannot_promote(tmp_path):
    store = RecoveryKnowledgeStore(tmp_path / "knowledge.json")
    store.add_candidate(
        knowledge_id="rk-1",
        incident_signature="sig:1",
        action_kind="investigate_only",
        recovery_summary="Inspect local evidence.",
        provenance="external:web",
        evidence_refs=["input:web"],
    )
    with pytest.raises(RecoveryKnowledgeError, match="Acceptance Gate"):
        store.promote_with_acceptance(
            "rk-1",
            acceptance_ref="acceptance:fake",
            acceptance_verdict="PASS",
            reviewer="external-source",
        )


def test_external_provenance_is_candidate_not_trusted(tmp_path):
    store = RecoveryKnowledgeStore(tmp_path / "knowledge.json")
    item = store.add_candidate(
        knowledge_id="rk-1",
        incident_signature="sig:1",
        action_kind="restart_service",
        recovery_summary="Untrusted external suggestion.",
        provenance="external:web",
        evidence_refs=["input:web"],
    )
    assert item["status"] == "candidate"
    assert item["trusted_for_auto_use"] is False
    assert store.recommend("sig:1") == []


def test_knowledge_hash_tamper_detected(tmp_path):
    path = tmp_path / "knowledge.json"
    store = RecoveryKnowledgeStore(path)
    store.add_candidate(
        knowledge_id="rk-1",
        incident_signature="sig:1",
        action_kind="minimal_patch",
        recovery_summary="Safe patch description.",
        provenance="runtime:test",
        evidence_refs=["test:hash"],
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    data[0]["recovery_summary"] = "poisoned content"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RecoveryKnowledgeError, match="hash mismatch"):
        store.all_entries()


def test_unsupported_action_kind_blocked(tmp_path):
    store = RecoveryKnowledgeStore(tmp_path / "knowledge.json")
    with pytest.raises(RecoveryKnowledgeError, match="unsupported"):
        store.add_candidate(
            knowledge_id="rk-1",
            incident_signature="sig:1",
            action_kind="execute_shell",
            recovery_summary="rm -rf something",
            provenance="external:web",
            evidence_refs=["input:web"],
        )
