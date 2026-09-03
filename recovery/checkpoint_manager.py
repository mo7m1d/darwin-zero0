from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CHECKPOINT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
SECRETISH_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "secrets.json",
    "id_rsa",
    "id_ed25519",
}
SECRETISH_PARTS = {"secrets", "credentials", ".ssh"}
MAX_CHECKPOINT_FILE_BYTES = 64 * 1024 * 1024
SCHEMA = "darwin.recovery.checkpoint.v1"
LEDGER_SCHEMA = "darwin.recovery.checkpoint-ledger.v1"


class CheckpointError(RuntimeError):
    pass


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _record_hash(record: dict[str, Any]) -> str:
    unsigned = dict(record)
    unsigned.pop("record_hash", None)
    return _sha256_bytes(_canonical_json(unsigned))


class CheckpointManager:
    """Integrity-first checkpoints for explicitly allowlisted runtime-state roots.

    This manager deliberately does not checkpoint arbitrary source trees, secrets,
    credentials, or Git metadata. Git remains the source recovery mechanism.
    Checkpoints are for mutable runtime state only.
    """

    def __init__(
        self,
        checkpoint_root: str | Path,
        allowed_roots: dict[str, str | Path],
        *,
        max_file_bytes: int = MAX_CHECKPOINT_FILE_BYTES,
    ):
        self.checkpoint_root = Path(checkpoint_root).resolve()
        self.checkpoint_root.mkdir(parents=True, exist_ok=True)
        self.allowed_roots = {
            root_id: Path(root).resolve()
            for root_id, root in allowed_roots.items()
        }
        if not self.allowed_roots:
            raise ValueError("allowed_roots must not be empty")
        for root_id in self.allowed_roots:
            if not CHECKPOINT_ID_RE.fullmatch(root_id):
                raise ValueError(f"invalid root id: {root_id}")
        self.max_file_bytes = int(max_file_bytes)
        if self.max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")
        self.ledger_path = self.checkpoint_root / "checkpoint-ledger.jsonl"

    @staticmethod
    def _is_secretish(path: Path) -> bool:
        name = path.name.casefold()
        if name in {x.casefold() for x in SECRETISH_NAMES} or name.startswith(".env"):
            return True
        parts = {part.casefold() for part in path.parts}
        return bool(parts & SECRETISH_PARTS)

    @staticmethod
    def _assert_no_symlink_components(path: Path, stop: Path) -> None:
        # Path.resolve() would hide the fact that the original path walked through
        # a symlink. Check existing components before trusting the resolved path.
        current = path
        while True:
            if current.exists() and current.is_symlink():
                raise CheckpointError(f"symlink path component is not checkpointable: {path}")
            if current == stop or current.parent == current:
                break
            current = current.parent

    def _locate_allowed_file(self, source: str | Path) -> tuple[str, Path, Path]:
        original = Path(source)
        if not original.exists():
            raise CheckpointError(f"checkpoint source does not exist: {source}")
        if not original.is_file():
            raise CheckpointError(f"checkpoint source is not a regular file: {source}")
        if self._is_secretish(original):
            raise CheckpointError(f"secret-like path is not checkpointable: {source}")

        for root_id, root in self.allowed_roots.items():
            try:
                self._assert_no_symlink_components(original.absolute(), root.absolute())
            except CheckpointError:
                raise

            resolved = original.resolve()
            try:
                rel = resolved.relative_to(root)
            except ValueError:
                continue

            if rel == Path("."):
                raise CheckpointError("allowed root itself is not a file path")
            if any(part in {"..", ""} for part in rel.parts):
                raise CheckpointError("unsafe checkpoint relative path")
            if self._is_secretish(rel):
                raise CheckpointError(f"secret-like path is not checkpointable: {source}")

            size = resolved.stat().st_size
            if size > self.max_file_bytes:
                raise CheckpointError(
                    f"checkpoint source exceeds size cap: {source} ({size} bytes)"
                )
            return root_id, resolved, rel

        raise CheckpointError(f"path is outside all checkpoint allowlisted roots: {source}")

    def _checkpoint_dir(self, checkpoint_id: str) -> Path:
        if not CHECKPOINT_ID_RE.fullmatch(checkpoint_id):
            raise CheckpointError(f"invalid checkpoint id: {checkpoint_id}")
        return self.checkpoint_root / checkpoint_id

    def _read_ledger(self) -> list[dict[str, Any]]:
        if not self.ledger_path.exists():
            return []
        records: list[dict[str, Any]] = []
        with self.ledger_path.open("r", encoding="utf-8") as handle:
            for line_no, raw in enumerate(handle, 1):
                raw = raw.strip()
                if not raw:
                    raise CheckpointError(f"blank ledger record at line {line_no}")
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise CheckpointError(f"invalid checkpoint ledger JSON at line {line_no}") from exc
                if not isinstance(record, dict):
                    raise CheckpointError(f"invalid checkpoint ledger record at line {line_no}")
                records.append(record)
        return records

    def verify_ledger(self) -> bool:
        records = self._read_ledger()
        previous = "0" * 64
        seen: set[str] = set()
        for index, record in enumerate(records, 1):
            if record.get("schema") != LEDGER_SCHEMA:
                raise CheckpointError(f"ledger schema mismatch at record {index}")
            if record.get("sequence") != index:
                raise CheckpointError(f"ledger sequence mismatch at record {index}")
            if record.get("previous_record_hash") != previous:
                raise CheckpointError(f"ledger chain mismatch at record {index}")
            checkpoint_id = str(record.get("checkpoint_id") or "")
            if checkpoint_id in seen:
                raise CheckpointError(f"duplicate checkpoint id in ledger: {checkpoint_id}")
            seen.add(checkpoint_id)
            expected = _record_hash(record)
            if record.get("record_hash") != expected:
                raise CheckpointError(f"ledger record hash mismatch at record {index}")
            previous = expected
        return True

    def _append_ledger_record(self, checkpoint_id: str, manifest_sha256: str) -> None:
        records = self._read_ledger()
        self.verify_ledger()
        previous = records[-1]["record_hash"] if records else "0" * 64
        record = {
            "schema": LEDGER_SCHEMA,
            "sequence": len(records) + 1,
            "checkpoint_id": checkpoint_id,
            "manifest_sha256": manifest_sha256,
            "previous_record_hash": previous,
            "recorded_at": _utcnow(),
        }
        record["record_hash"] = _record_hash(record)
        with self.ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def create_checkpoint(
        self,
        checkpoint_id: str,
        files: list[str | Path],
        *,
        provenance: str,
        evidence_refs: list[str],
    ) -> dict[str, Any]:
        target = self._checkpoint_dir(checkpoint_id)
        if target.exists():
            raise CheckpointError(f"checkpoint already exists: {checkpoint_id}")
        if not files:
            raise CheckpointError("checkpoint file list must not be empty")
        if not provenance or not provenance.strip():
            raise CheckpointError("checkpoint provenance is required")
        if not evidence_refs or any(not str(ref).strip() for ref in evidence_refs):
            raise CheckpointError("checkpoint evidence_refs must contain non-empty refs")

        entries: list[dict[str, Any]] = []
        seen_destinations: set[tuple[str, str]] = set()
        tmp = self.checkpoint_root / f".{checkpoint_id}.tmp"
        if tmp.exists():
            raise CheckpointError(f"stale checkpoint temp directory exists: {tmp}")
        payload_root = tmp / "payload"

        try:
            payload_root.mkdir(parents=True)
            for source in files:
                root_id, resolved, rel = self._locate_allowed_file(source)
                key = (root_id, rel.as_posix())
                if key in seen_destinations:
                    raise CheckpointError(f"duplicate checkpoint path: {key}")
                seen_destinations.add(key)

                payload = payload_root / root_id / rel
                payload.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(resolved, payload)
                entries.append(
                    {
                        "root_id": root_id,
                        "relative_path": rel.as_posix(),
                        "sha256": _sha256_file(payload),
                        "bytes": payload.stat().st_size,
                    }
                )

            entries.sort(key=lambda item: (item["root_id"], item["relative_path"]))
            manifest = {
                "schema": SCHEMA,
                "checkpoint_id": checkpoint_id,
                "created_at": _utcnow(),
                "provenance": provenance.strip(),
                "evidence_refs": [str(ref).strip() for ref in evidence_refs],
                "files": entries,
            }
            manifest_bytes = _canonical_json(manifest)
            manifest_hash = _sha256_bytes(manifest_bytes)

            (tmp / "manifest.json").write_bytes(manifest_bytes + b"\n")
            (tmp / "manifest.sha256").write_text(
                manifest_hash + "\n",
                encoding="utf-8",
                newline="\n",
            )

            # Atomic visibility: checkpoint becomes visible only after all payload
            # and manifest bytes exist.
            os.replace(tmp, target)
            self._append_ledger_record(checkpoint_id, manifest_hash)
        except Exception:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            raise

        self.verify_checkpoint(checkpoint_id)
        self.verify_ledger()
        return manifest

    def verify_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        target = self._checkpoint_dir(checkpoint_id)
        manifest_path = target / "manifest.json"
        hash_path = target / "manifest.sha256"
        payload_root = target / "payload"
        if not manifest_path.is_file() or not hash_path.is_file() or not payload_root.is_dir():
            raise CheckpointError(f"checkpoint structure incomplete: {checkpoint_id}")

        raw = manifest_path.read_bytes().rstrip(b"\r\n")
        expected_manifest_hash = hash_path.read_text(encoding="utf-8").strip()
        actual_manifest_hash = _sha256_bytes(raw)
        if actual_manifest_hash != expected_manifest_hash:
            raise CheckpointError(f"checkpoint manifest hash mismatch: {checkpoint_id}")

        try:
            manifest = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CheckpointError(f"checkpoint manifest is invalid: {checkpoint_id}") from exc

        if manifest.get("schema") != SCHEMA or manifest.get("checkpoint_id") != checkpoint_id:
            raise CheckpointError(f"checkpoint manifest identity mismatch: {checkpoint_id}")

        expected_payloads: set[str] = set()
        for entry in manifest.get("files", []):
            if not isinstance(entry, dict):
                raise CheckpointError("invalid checkpoint file entry")
            root_id = str(entry.get("root_id") or "")
            rel_text = str(entry.get("relative_path") or "")
            if root_id not in self.allowed_roots:
                raise CheckpointError(f"unknown root id in checkpoint manifest: {root_id}")
            rel = Path(rel_text)
            if rel.is_absolute() or ".." in rel.parts or self._is_secretish(rel):
                raise CheckpointError(f"unsafe checkpoint manifest path: {rel_text}")
            payload = payload_root / root_id / rel
            try:
                payload.resolve().relative_to(payload_root.resolve())
            except ValueError as exc:
                raise CheckpointError(f"checkpoint payload escapes payload root: {rel_text}") from exc
            if not payload.is_file():
                raise CheckpointError(f"checkpoint payload missing: {root_id}/{rel_text}")
            if payload.is_symlink():
                raise CheckpointError(f"checkpoint payload must not be a symlink: {rel_text}")
            if payload.stat().st_size != int(entry.get("bytes", -1)):
                raise CheckpointError(f"checkpoint payload size mismatch: {rel_text}")
            if _sha256_file(payload) != entry.get("sha256"):
                raise CheckpointError(f"checkpoint payload hash mismatch: {rel_text}")
            expected_payloads.add((Path(root_id) / rel).as_posix())

        actual_payloads = {
            p.relative_to(payload_root).as_posix()
            for p in payload_root.rglob("*")
            if p.is_file()
        }
        if actual_payloads != expected_payloads:
            raise CheckpointError(
                f"checkpoint payload surface mismatch: expected={sorted(expected_payloads)} "
                f"actual={sorted(actual_payloads)}"
            )

        ledger_records = self._read_ledger()
        matches = [
            record for record in ledger_records
            if record.get("checkpoint_id") == checkpoint_id
        ]
        if len(matches) != 1:
            raise CheckpointError(f"checkpoint ledger record count mismatch: {checkpoint_id}")
        if matches[0].get("manifest_sha256") != expected_manifest_hash:
            raise CheckpointError(f"checkpoint ledger/manifest mismatch: {checkpoint_id}")

        return manifest

    def plan_restore(
        self,
        checkpoint_id: str,
        *,
        expected_current_hashes: dict[str, str | None],
    ) -> list[dict[str, Any]]:
        manifest = self.verify_checkpoint(checkpoint_id)
        self.verify_ledger()
        actions: list[dict[str, Any]] = []

        for entry in manifest["files"]:
            root_id = entry["root_id"]
            rel = Path(entry["relative_path"])
            destination = self.allowed_roots[root_id] / rel
            key = f"{root_id}:{rel.as_posix()}"
            if key not in expected_current_hashes:
                raise CheckpointError(f"restore lacks expected-current hash guard: {key}")

            expected_current = expected_current_hashes[key]
            if destination.exists():
                if not destination.is_file() or destination.is_symlink():
                    raise CheckpointError(f"unsafe restore destination: {destination}")
                current = _sha256_file(destination)
                if expected_current is None or current != expected_current:
                    raise CheckpointError(
                        f"restore stale-write guard blocked changed target: {key}"
                    )
            else:
                if expected_current is not None:
                    raise CheckpointError(
                        f"restore expected an existing target but it is missing: {key}"
                    )

            actions.append(
                {
                    "root_id": root_id,
                    "relative_path": rel.as_posix(),
                    "destination": str(destination),
                    "checkpoint_sha256": entry["sha256"],
                    "expected_current_sha256": expected_current,
                }
            )

        return actions

    def restore_checkpoint(
        self,
        checkpoint_id: str,
        *,
        expected_current_hashes: dict[str, str | None],
        owner_authorized: bool,
    ) -> list[dict[str, Any]]:
        if not owner_authorized:
            raise CheckpointError("restore requires explicit owner authorization")

        actions = self.plan_restore(
            checkpoint_id,
            expected_current_hashes=expected_current_hashes,
        )
        checkpoint_dir = self._checkpoint_dir(checkpoint_id)
        restored: list[dict[str, Any]] = []

        # Copy through temporary sibling files and atomically replace each target.
        for action in actions:
            root_id = action["root_id"]
            rel = Path(action["relative_path"])
            source = checkpoint_dir / "payload" / root_id / rel
            destination = Path(action["destination"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            tmp = destination.with_name(destination.name + ".darwin-restore.tmp")
            if tmp.exists():
                raise CheckpointError(f"stale restore temp file exists: {tmp}")
            shutil.copy2(source, tmp)
            if _sha256_file(tmp) != action["checkpoint_sha256"]:
                tmp.unlink(missing_ok=True)
                raise CheckpointError(f"restore temp hash mismatch: {destination}")
            os.replace(tmp, destination)
            restored.append(action)

        return restored
