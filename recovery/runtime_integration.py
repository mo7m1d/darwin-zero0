from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .checkpoint_manager import CheckpointError, CheckpointManager
from .recovery_knowledge import RecoveryKnowledgeError, RecoveryKnowledgeStore

PROFILE_SCHEMA = "darwin.recovery.runtime-profile.v1"
RECEIPT_SCHEMA = "darwin.acceptance.receipt.v1"
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
SECRET_RE = re.compile(
    r"(?i)(^|[\\/])(\.env[^\\/]*|credentials?[^\\/]*|secrets?[^\\/]*|tokens?[^\\/]*|auth(?:\.json)?|id_rsa|id_ed25519|[^\\/]*\.(?:pem|key|p12|pfx))([\\/]|$)"
)
EXECUTABLE_TEXT_RE = re.compile(
    r"(?i)(?:\b(?:powershell|pwsh|cmd(?:\.exe)?|bash|sh|curl|wget|python|node)\b|\brm\s+-|\bdel\s+|\bremove-item\b|\|\s*(?:sh|bash|pwsh|powershell)\b|```|<script)"
)

ALLOWLIST = (
    {"id": "runtime_telemetry", "relative_path": "darwin/telemetry/events.sqlite3", "type": "sqlite", "max_bytes": 64 * 1024 * 1024, "restore": "archive_only", "optional": False},
    {"id": "control_supervisor", "relative_path": "darwin/supervisor/decisions.sqlite3", "type": "sqlite", "max_bytes": 64 * 1024 * 1024, "restore": "archive_only", "optional": False},
    {"id": "kanban_board", "relative_path": "kanban/boards/darwin-zero0/kanban.db", "type": "sqlite", "max_bytes": 64 * 1024 * 1024, "restore": "archive_only", "optional": False},
    {"id": "kanban_board_metadata", "relative_path": "kanban/boards/darwin-zero0/board.json", "type": "json", "max_bytes": 1024 * 1024, "restore": "owner_restore", "optional": False},
    {"id": "acceptance_ledger", "relative_path": "darwin/acceptance/acceptance.sqlite3", "type": "sqlite", "max_bytes": 64 * 1024 * 1024, "restore": "archive_only", "optional": True},
    {"id": "verification_evidence", "relative_path": "verification_evidence.db", "type": "sqlite", "max_bytes": 64 * 1024 * 1024, "restore": "archive_only", "optional": False},
    {"id": "spawn_ledger", "relative_path": "spawn-ledger.json", "type": "json", "max_bytes": 1024 * 1024, "restore": "archive_only", "optional": False},
    {"id": "recovery_knowledge", "relative_path": "darwin/recovery/knowledge/recovery-knowledge.json", "type": "json", "max_bytes": 8 * 1024 * 1024, "restore": "owner_restore", "optional": True},
    {"id": "recovery_retry_history", "relative_path": "darwin/recovery/attempts/retry-history.json", "type": "json", "max_bytes": 8 * 1024 * 1024, "restore": "never_restore", "optional": True},
)
ALLOWLIST_BY_ID = {item["id"]: item for item in ALLOWLIST}


class RecoveryIntegrationError(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_path(path: Path) -> None:
    if SECRET_RE.search(str(path)):
        raise RecoveryIntegrationError("secret-like path rejected")
    current = path.absolute()
    while current.parent != current:
        if current.exists() and current.is_symlink():
            raise RecoveryIntegrationError("symlink traversal rejected")
        current = current.parent


def build_candidate_profile(
    *,
    state_root: Path,
    checkpoint_root: Path,
    live_hermes_home: Path,
    canonical_head: str,
    hermes_head: str,
    plugin_versions: dict[str, str],
    approvals_mode: str,
    integration_registry_ref: str,
    integration_registry_sha256: str,
) -> dict[str, Any]:
    state_root = state_root.resolve()
    checkpoint_root = checkpoint_root.resolve()
    live_hermes_home = live_hermes_home.resolve()
    live_recovery = live_hermes_home / "darwin" / "recovery"
    if _inside(checkpoint_root, live_recovery):
        raise RecoveryIntegrationError("candidate/live recovery path confusion")
    if not HASH_RE.fullmatch(canonical_head) or not HASH_RE.fullmatch(hermes_head):
        raise RecoveryIntegrationError("invalid Git provenance")
    if not HASH_RE.fullmatch(integration_registry_sha256):
        raise RecoveryIntegrationError("invalid Integration Registry hash")
    if approvals_mode != "manual":
        raise RecoveryIntegrationError("approvals.mode must remain manual")
    safe_versions = {str(k): str(v) for k, v in plugin_versions.items()}
    entries = []
    for item in ALLOWLIST:
        rel = Path(item["relative_path"])
        if rel.is_absolute() or ".." in rel.parts or SECRET_RE.search(item["relative_path"]):
            raise RecoveryIntegrationError("unsafe built-in allowlist")
        entries.append({**item, "path": str(state_root / rel)})
    return {
        "schema": PROFILE_SCHEMA,
        "mode": "isolated_candidate",
        "state_root": str(state_root),
        "checkpoint_root": str(checkpoint_root),
        "live_recovery_root": str(live_recovery),
        "source_recovery": "git_only",
        "entries": entries,
        "excluded": [".env*", "credential*", "secret*", "token*", ".ssh", "*.pem", "*.key", "SQLite sidecars", "locks", "source code", ".git"],
        "provenance": {
            "canonical_git_head": canonical_head,
            "hermes_git_head": hermes_head,
            "plugin_versions": safe_versions,
            "safe_config_flags": {"approvals.mode": "manual"},
            "integration_registry": {"ref": integration_registry_ref, "sha256": integration_registry_sha256},
        },
    }


def validate_profile(profile: dict[str, Any]) -> bool:
    if profile.get("schema") != PROFILE_SCHEMA or profile.get("mode") != "isolated_candidate":
        raise RecoveryIntegrationError("profile identity rejected")
    if profile.get("source_recovery") != "git_only":
        raise RecoveryIntegrationError("source recovery must remain Git-backed")
    state_root = Path(str(profile.get("state_root") or ""))
    checkpoint_root = Path(str(profile.get("checkpoint_root") or ""))
    live_root = Path(str(profile.get("live_recovery_root") or ""))
    if not state_root.is_absolute() or not checkpoint_root.is_absolute() or _inside(checkpoint_root, live_root):
        raise RecoveryIntegrationError("candidate/live path confusion")
    entries = profile.get("entries")
    if not isinstance(entries, list) or len(entries) != len(ALLOWLIST):
        raise RecoveryIntegrationError("poisoned recovery profile")
    seen: set[str] = set()
    for entry in entries:
        root_id = str(entry.get("id") or "")
        expected = ALLOWLIST_BY_ID.get(root_id)
        if expected is None or root_id in seen:
            raise RecoveryIntegrationError("unknown runtime-state root")
        seen.add(root_id)
        for key in ("relative_path", "type", "max_bytes", "restore", "optional"):
            if entry.get(key) != expected[key]:
                raise RecoveryIntegrationError("poisoned recovery profile")
        rel = Path(entry["relative_path"])
        if rel.is_absolute() or ".." in rel.parts or SECRET_RE.search(entry["relative_path"]):
            raise RecoveryIntegrationError("unsafe recovery profile path")
        expected_path = (state_root / rel).resolve()
        if Path(str(entry.get("path") or "")).resolve() != expected_path:
            raise RecoveryIntegrationError("recovery profile path mismatch")
        if entry["type"] == "source" or expected_path.suffix.casefold() in {".py", ".ps1", ".sh", ".exe", ".dll"}:
            raise RecoveryIntegrationError("source-code checkpoint profile rejected")
    provenance = profile.get("provenance") or {}
    if (provenance.get("safe_config_flags") or {}).get("approvals.mode") != "manual":
        raise RecoveryIntegrationError("unsafe config provenance")
    return True


class IntegratedRecoveryManager:
    def __init__(self, profile: dict[str, Any]):
        validate_profile(profile)
        self.profile = profile
        self.entries = {entry["id"]: entry for entry in profile["entries"]}
        roots = {root_id: Path(entry["path"]).parent for root_id, entry in self.entries.items()}
        self.base = CheckpointManager(profile["checkpoint_root"], roots)

    def create_checkpoint(self, checkpoint_id: str, include_ids: list[str], evidence_refs: list[str]) -> dict[str, Any]:
        if not include_ids or len(include_ids) != len(set(include_ids)):
            raise RecoveryIntegrationError("explicit unique runtime root ids required")
        paths: list[Path] = []
        before: dict[str, str] = {}
        for root_id in include_ids:
            entry = self.entries.get(root_id)
            if entry is None:
                raise RecoveryIntegrationError("unknown runtime-state root")
            path = Path(entry["path"])
            _safe_path(path)
            if not path.is_file():
                raise RecoveryIntegrationError("allowlisted runtime file unavailable")
            if path.stat().st_size > int(entry["max_bytes"]):
                raise RecoveryIntegrationError("runtime file exceeds profile size limit")
            paths.append(path)
            before[root_id] = file_sha256(path)
        provenance = json.dumps(self.profile["provenance"], sort_keys=True, separators=(",", ":"))
        manifest = self.base.create_checkpoint(checkpoint_id, paths, provenance=provenance, evidence_refs=evidence_refs)
        for root_id in include_ids:
            if file_sha256(Path(self.entries[root_id]["path"])) != before[root_id]:
                raise RecoveryIntegrationError("checkpoint source mutated during capture")
        return manifest

    def restore_checkpoint(self, checkpoint_id: str, *, expected_current_hashes: dict[str, str | None], owner_authorized: bool) -> list[dict[str, Any]]:
        manifest = self.base.verify_checkpoint(checkpoint_id)
        translated: dict[str, str | None] = {}
        for item in manifest["files"]:
            destination = (self.base.allowed_roots[item["root_id"]] / item["relative_path"]).resolve()
            matches = [entry for entry in self.entries.values() if Path(entry["path"]).resolve() == destination]
            if len(matches) != 1:
                raise RecoveryIntegrationError("checkpoint entry is not an exact allowlisted file")
            entry = matches[0]
            if entry["restore"] != "owner_restore":
                raise RecoveryIntegrationError("ledger or retry state is archive-only and cannot be restored")
            external_key = f'{entry["id"]}:{Path(entry["path"]).name}'
            if external_key not in expected_current_hashes:
                raise CheckpointError(f"restore lacks expected-current hash guard: {external_key}")
            translated[f'{item["root_id"]}:{item["relative_path"]}'] = expected_current_hashes[external_key]
        return self.base.restore_checkpoint(checkpoint_id, expected_current_hashes=translated, owner_authorized=owner_authorized)


class StrictRecoveryKnowledge:
    def __init__(self, path: Path, acceptance_root: Path):
        self.store = RecoveryKnowledgeStore(path)
        self.acceptance_root = acceptance_root.resolve()

    def add_candidate(self, **kwargs: Any) -> dict[str, Any]:
        summary = str(kwargs.get("recovery_summary") or "")
        if EXECUTABLE_TEXT_RE.search(summary):
            raise RecoveryKnowledgeError("executable recovery text rejected")
        return self.store.add_candidate(**kwargs)

    def promote_with_verified_acceptance(self, knowledge_id: str, *, receipt_path: Path, expected_sha256: str, acceptance_ref: str) -> dict[str, Any]:
        _safe_path(receipt_path)
        if not _inside(receipt_path, self.acceptance_root) or not receipt_path.is_file():
            raise RecoveryKnowledgeError("Acceptance evidence path rejected")
        if not HASH_RE.fullmatch(expected_sha256) or file_sha256(receipt_path) != expected_sha256:
            raise RecoveryKnowledgeError("Acceptance evidence hash mismatch")
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RecoveryKnowledgeError("Acceptance evidence invalid") from exc
        if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("verdict") != "PASS" or receipt.get("acceptance_ref") != acceptance_ref:
            raise RecoveryKnowledgeError("Acceptance PASS evidence required")
        return self.store.promote_with_acceptance(knowledge_id, acceptance_ref=acceptance_ref, acceptance_verdict="PASS")
