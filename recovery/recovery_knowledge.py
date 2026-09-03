from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "darwin.recovery.knowledge.v1"
SAFE_ACTION_KINDS = {
    "minimal_patch",
    "restart_service",
    "restore_checkpoint",
    "config_rollback",
    "investigate_only",
}


class RecoveryKnowledgeError(RuntimeError):
    pass


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _hash_entry(entry: dict[str, Any]) -> str:
    unsigned = dict(entry)
    unsigned.pop("entry_hash", None)
    return hashlib.sha256(_canonical_json(unsigned)).hexdigest()


class RecoveryKnowledgeStore:
    """Data-only recovery memory.

    External observations may create candidates, but candidates are never trusted
    automatically. Trust requires Acceptance-Gate evidence and provenance. This
    store never executes recovery text or imports code from knowledge entries.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RecoveryKnowledgeError("recovery knowledge store is invalid JSON") from exc
        if not isinstance(data, list):
            raise RecoveryKnowledgeError("recovery knowledge store must be a list")
        for entry in data:
            if not isinstance(entry, dict) or entry.get("schema") != SCHEMA:
                raise RecoveryKnowledgeError("recovery knowledge entry schema mismatch")
            if entry.get("entry_hash") != _hash_entry(entry):
                raise RecoveryKnowledgeError("recovery knowledge entry hash mismatch")
        return data

    def _save(self, entries: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(entries, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        tmp.replace(self.path)

    def add_candidate(
        self,
        *,
        knowledge_id: str,
        incident_signature: str,
        action_kind: str,
        recovery_summary: str,
        provenance: str,
        evidence_refs: list[str],
    ) -> dict[str, Any]:
        if action_kind not in SAFE_ACTION_KINDS:
            raise RecoveryKnowledgeError(f"unsupported recovery action kind: {action_kind}")
        if not knowledge_id or not incident_signature or not recovery_summary.strip():
            raise RecoveryKnowledgeError("knowledge id, signature, and summary are required")
        if not provenance.strip():
            raise RecoveryKnowledgeError("recovery knowledge provenance is required")
        if not evidence_refs or any(not str(ref).strip() for ref in evidence_refs):
            raise RecoveryKnowledgeError("candidate recovery knowledge requires evidence refs")

        entries = self._load()
        if any(entry.get("knowledge_id") == knowledge_id for entry in entries):
            raise RecoveryKnowledgeError(f"duplicate recovery knowledge id: {knowledge_id}")

        entry = {
            "schema": SCHEMA,
            "knowledge_id": knowledge_id,
            "incident_signature": incident_signature,
            "action_kind": action_kind,
            "recovery_summary": recovery_summary.strip(),
            "provenance": provenance.strip(),
            "evidence_refs": [str(ref).strip() for ref in evidence_refs],
            "status": "candidate",
            "trusted_for_auto_use": False,
            "acceptance_ref": None,
            "reviewed_at": None,
            "created_at": _utcnow(),
        }
        entry["entry_hash"] = _hash_entry(entry)
        entries.append(entry)
        self._save(entries)
        return dict(entry)

    def promote_with_acceptance(
        self,
        knowledge_id: str,
        *,
        acceptance_ref: str,
        acceptance_verdict: str,
        reviewer: str = "darwin-acceptance-gate",
    ) -> dict[str, Any]:
        if reviewer != "darwin-acceptance-gate":
            raise RecoveryKnowledgeError("only the Acceptance Gate may promote recovery knowledge")
        if acceptance_verdict != "PASS":
            raise RecoveryKnowledgeError("recovery knowledge trust requires PASS acceptance")
        if not acceptance_ref.startswith("acceptance:"):
            raise RecoveryKnowledgeError("acceptance_ref must use acceptance: provenance")

        entries = self._load()
        for entry in entries:
            if entry.get("knowledge_id") != knowledge_id:
                continue
            entry["status"] = "trusted"
            entry["trusted_for_auto_use"] = True
            entry["acceptance_ref"] = acceptance_ref
            entry["reviewed_at"] = _utcnow()
            entry["entry_hash"] = _hash_entry(entry)
            self._save(entries)
            return dict(entry)
        raise RecoveryKnowledgeError(f"recovery knowledge id not found: {knowledge_id}")

    def recommend(self, incident_signature: str) -> list[dict[str, Any]]:
        entries = self._load()
        trusted = [
            dict(entry)
            for entry in entries
            if entry.get("incident_signature") == incident_signature
            and entry.get("status") == "trusted"
            and entry.get("trusted_for_auto_use") is True
            and str(entry.get("acceptance_ref") or "").startswith("acceptance:")
        ]
        return trusted

    def all_entries(self) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self._load()]
