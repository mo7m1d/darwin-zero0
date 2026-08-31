#!/usr/bin/env python3
"""DARWIN ZERO-0 Execution Discipline Protocol + Loop Breaker / Recovery Guard.

This module provides high-level incident memory, recovery discipline, destructive
operation policy, and loop escalation. The canonical API is instance-based:

    engine = ExecutionDisciplineEngine(incident_store_path=...)
    engine.record_attempt(...)
    engine.block_source_deletion(...)
    engine.allow_safe_patch(...)

Production runtime state is stored in ``core/execution_discipline_incidents.json``.
Tests should always inject an isolated temporary ``incident_store_path``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INCIDENT_MEMORIES_PATH = Path(__file__).parent / "execution_discipline_incidents.json"
LOOP_DETECTION_THRESHOLD = 3

STATUS_OPEN = "open"
STATUS_RESOLVED = "resolved"
STATUS_ESCALATED = "escalated"

ERROR_TYPES = {
    "syntax_error": "python syntax error",
    "indentation": "indentation error",
    "import_error": "import error",
    "key_error": "key error",
    "value_error": "value error",
    "type_error": "type error",
    "file_not_found": "file not found",
    "permission_error": "permission error",
}

SAFE_PATCH_MARKER = "safe_minimal_patch"
DESTRUCTIVE_OPERATION = "destructive"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_error_message(error_type: str, message: str) -> str:
    """Normalize variable details while preserving the meaningful error text."""
    cleaned = str(message or "")
    cleaned = re.sub(r"\s+on\s+line\s+\d+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'File\s+"[^"]+",\s*line\s+\d+', "File <path>", cleaned)
    cleaned = re.sub(r"(?m)^\s*\^\s*$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return f"{error_type}:{cleaned}"


class IncidentRecord:
    """Serializable execution-discipline incident."""

    def __init__(
        self,
        incident_id: str,
        task: str,
        file_path: str,
        exact_error: str,
        error_type: str,
        *,
        detected_at: str | None = None,
        root_cause: str | None = None,
        failed_approaches: list[dict[str, Any]] | None = None,
        successful_recovery: str | None = None,
        recovery_pattern: str | None = None,
        verification_evidence: list[str] | None = None,
        resolution_status: str = STATUS_OPEN,
        attempts: int = 0,
        resolved_at: str | None = None,
    ):
        self.incident_id = incident_id
        self.detected_at = detected_at or _utcnow()
        self.task = task
        self.file_path = file_path
        self.exact_error = exact_error
        self.error_type = error_type
        self.normalized_error = normalize_error_message(error_type, exact_error)
        self.root_cause = root_cause
        self.failed_approaches = list(failed_approaches or [])
        self.successful_recovery = successful_recovery
        self.recovery_pattern = recovery_pattern
        self.verification_evidence = list(verification_evidence or [])
        self.resolution_status = resolution_status
        self.attempts = int(attempts)
        self.resolved_at = resolved_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "detected_at": self.detected_at,
            "task": self.task,
            "file_path": self.file_path,
            "exact_error": self.exact_error,
            "error_type": self.error_type,
            "normalized_error": self.normalized_error,
            "root_cause": self.root_cause,
            "failed_approaches": self.failed_approaches,
            "successful_recovery": self.successful_recovery,
            "recovery_pattern": self.recovery_pattern,
            "verification_evidence": self.verification_evidence,
            "resolution_status": self.resolution_status,
            "attempts": self.attempts,
            "resolved_at": self.resolved_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IncidentRecord":
        return cls(
            incident_id=data["incident_id"],
            detected_at=data.get("detected_at"),
            task=data.get("task", ""),
            file_path=data.get("file_path", ""),
            exact_error=data.get("exact_error", ""),
            error_type=data.get("error_type", "unknown"),
            root_cause=data.get("root_cause"),
            failed_approaches=data.get("failed_approaches", []),
            successful_recovery=data.get("successful_recovery"),
            recovery_pattern=data.get("recovery_pattern"),
            verification_evidence=data.get("verification_evidence", []),
            resolution_status=data.get("resolution_status", STATUS_OPEN),
            attempts=data.get("attempts", 0),
            resolved_at=data.get("resolved_at"),
        )


class ExecutionDisciplineEngine:
    """Execution discipline, incident memory, and recovery guard."""

    def __init__(
        self,
        state_manager=None,
        event_dispatcher=None,
        incident_store_path: str | Path | None = None,
    ):
        self.state_manager = state_manager
        self.event_dispatcher = event_dispatcher
        self.incident_store_path = Path(
            incident_store_path if incident_store_path is not None else INCIDENT_MEMORIES_PATH
        )
        self.incidents = self._load_memories()
        self._incident_index: dict[tuple[str, str], list[IncidentRecord]] = {}
        self._index_incidents()

    def _load_memories(self) -> list[IncidentRecord]:
        if not self.incident_store_path.exists():
            return []
        try:
            with self.incident_store_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            records = []
            for item in data:
                if isinstance(item, IncidentRecord):
                    records.append(item)
                elif isinstance(item, dict) and item.get("incident_id"):
                    records.append(IncidentRecord.from_dict(item))
            return records
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return []

    def _save_memories(self) -> None:
        self.incident_store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [incident.to_dict() for incident in self.incidents]
        temp_path = self.incident_store_path.with_suffix(
            self.incident_store_path.suffix + ".tmp"
        )
        with temp_path.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        temp_path.replace(self.incident_store_path)

    def _index_incidents(self) -> None:
        self._incident_index = {}
        for incident in self.incidents:
            key = (incident.error_type, incident.normalized_error)
            self._incident_index.setdefault(key, []).append(incident)

    def _emit_event(self, method_name: str, **kwargs) -> None:
        if self.event_dispatcher is None:
            return
        method = getattr(self.event_dispatcher, method_name, None)
        if callable(method):
            method(**kwargs)

    def _find_incident(self, incident_id: str) -> IncidentRecord | None:
        for incident in self.incidents:
            if incident.incident_id == incident_id:
                return incident
        return None

    def record_attempt(
        self,
        incident_id: str,
        task: str,
        file_path: str,
        exact_error: str,
        error_type: str,
        approach_description: str | None = None,
    ) -> IncidentRecord:
        """Record one recovery attempt and persist it.

        ``incident_id`` is the caller-owned unique identifier. Reusing an ID for a
        different file is rejected instead of silently merging unrelated incidents.
        """
        incident = self._find_incident(incident_id)
        now = _utcnow()

        approach = {
            "approach": approach_description or "unknown",
            "attempted_at": now,
        }

        if incident is None:
            incident = IncidentRecord(
                incident_id=incident_id,
                task=task,
                file_path=file_path,
                exact_error=exact_error,
                error_type=error_type,
                failed_approaches=[approach],
                attempts=1,
            )
            self.incidents.append(incident)
            self._emit_event(
                "incident_detected",
                signature=f"exec_discipline:{incident.incident_id}",
                severity="medium",
                source="execution_discipline_engine",
            )
        else:
            if incident.file_path != file_path:
                raise ValueError(
                    f"Incident ID '{incident_id}' is already associated with "
                    f"'{incident.file_path}', not '{file_path}'."
                )
            incident.task = task
            incident.exact_error = exact_error
            incident.error_type = error_type
            incident.normalized_error = normalize_error_message(error_type, exact_error)
            incident.attempts += 1
            incident.failed_approaches.append(approach)

        self._emit_event(
            "recovery_attempted",
            signature=f"exec_discipline:{incident.incident_id}",
            severity="medium",
            source="execution_discipline_engine",
            details=f"attempt={incident.attempts}",
        )

        self._index_incidents()
        self._save_memories()
        return incident

    def detect_loop(
        self,
        error_type: str,
        normalized_error: str,
        file_path: str | None = None,
    ) -> tuple[bool, IncidentRecord | None, int]:
        key = (error_type, normalized_error)
        incidents = self._incident_index.get(key, [])
        if file_path is not None:
            incidents = [i for i in incidents if i.file_path == file_path]
        if not incidents:
            return False, None, 0

        unresolved = [
            incident for incident in incidents
            if incident.resolution_status != STATUS_RESOLVED
        ]
        if unresolved:
            most_recent = max(unresolved, key=lambda i: i.detected_at)
            return (
                most_recent.attempts >= LOOP_DETECTION_THRESHOLD,
                most_recent,
                most_recent.attempts,
            )

        most_recent = max(incidents, key=lambda i: i.detected_at)
        return False, most_recent, most_recent.attempts

    def check_and_block(
        self,
        error_type: str,
        normalized_error: str,
        file_path: str | None = None,
    ) -> tuple[bool, IncidentRecord | None, str]:
        is_loop, incident, attempts = self.detect_loop(
            error_type, normalized_error, file_path
        )
        if is_loop and incident is not None:
            message = (
                f"LOOP_DETECTED: {error_type} '{incident.normalized_error}' on "
                f"{incident.file_path} has {incident.attempts} attempts "
                f"(threshold: {LOOP_DETECTION_THRESHOLD}). Mutations blocked."
            )
            self._emit_event(
                "loop_detected",
                signature=f"exec_discipline:{incident.incident_id}",
                severity="high",
                source="execution_discipline_engine",
                details=message,
            )
            self._emit_event(
                "owner_escalation_required",
                signature=f"exec_discipline:{incident.incident_id}",
                severity="high",
                source="execution_discipline_engine",
                details=message,
            )
            return True, incident, message
        return (
            False,
            incident,
            f"Attempt {attempts}/{LOOP_DETECTION_THRESHOLD} — continuing",
        )

    def block_source_deletion(
        self,
        file_path: str,
        task: str,
        *,
        owner_approved: bool = False,
    ) -> tuple[bool, str]:
        """Block source/test deletion unless the owner explicitly approved it."""
        if owner_approved:
            return False, f"OWNER APPROVED deletion for {file_path}: {task}"
        return (
            True,
            f"SOURCE/TEST DELETION BLOCKED: {file_path}. "
            "Explicit owner approval is required; use a minimal patch instead.",
        )

    def allow_safe_patch(self, file_path: str, task: str) -> tuple[bool, str]:
        """Allow minimal patches unless an unresolved loop already hit threshold."""
        active = [
            incident
            for incident in self.incidents
            if incident.file_path == file_path
            and incident.resolution_status != STATUS_RESOLVED
            and incident.attempts >= LOOP_DETECTION_THRESHOLD
        ]
        if active:
            latest = max(active, key=lambda i: i.detected_at)
            return (
                False,
                f"PATCH BLOCKED: {file_path} has {latest.attempts} failed attempts "
                f"(threshold: {LOOP_DETECTION_THRESHOLD}). Escalate before continuing.",
            )
        return (
            True,
            "SAFE PATCH ALLOWED: no unresolved loop at threshold; "
            "use a minimal patch and targeted verification.",
        )

    def resolve_incident(
        self,
        incident_id: str,
        resolution_status: str = STATUS_RESOLVED,
        successful_recovery: str | None = None,
        recovery_pattern: str | None = None,
        verification_evidence: list[str] | None = None,
    ) -> IncidentRecord | None:
        incident = self._find_incident(incident_id)
        if incident is None:
            return None
        incident.resolution_status = resolution_status
        incident.successful_recovery = successful_recovery
        incident.recovery_pattern = recovery_pattern
        if verification_evidence is not None:
            incident.verification_evidence = list(verification_evidence)
        incident.resolved_at = _utcnow()
        self._save_memories()
        self._index_incidents()
        self._emit_event(
            "recovery_succeeded",
            signature=f"exec_discipline:{incident.incident_id}",
            severity="low",
            source="execution_discipline_engine",
            details=successful_recovery or "Recovery completed",
        )
        return incident

    def fail_incident(
        self,
        incident_id: str,
        reason: str = "Recovery failed",
    ) -> IncidentRecord | None:
        incident = self._find_incident(incident_id)
        if incident is None:
            return None
        incident.resolution_status = STATUS_ESCALATED
        incident.successful_recovery = reason
        incident.resolved_at = _utcnow()
        self._save_memories()
        self._index_incidents()
        self._emit_event(
            "recovery_failed",
            signature=f"exec_discipline:{incident.incident_id}",
            severity="medium",
            source="execution_discipline_engine",
            details=reason,
        )
        self._emit_event(
            "owner_escalation_required",
            signature=f"exec_discipline:{incident.incident_id}",
            severity="high",
            source="execution_discipline_engine",
            details=reason,
        )
        return incident


def init_discipline_engine(
    state_manager=None,
    event_dispatcher=None,
    incident_store_path: str | Path | None = None,
) -> ExecutionDisciplineEngine:
    return ExecutionDisciplineEngine(
        state_manager=state_manager,
        event_dispatcher=event_dispatcher,
        incident_store_path=incident_store_path,
    )


def record_syntax_error_incident(
    incident_id: str,
    task: str,
    file_path: str,
    exact_error: str,
    error_type: str = "syntax_error",
    approach_description: str | None = None,
    *,
    engine: ExecutionDisciplineEngine | None = None,
    incident_store_path: str | Path | None = None,
) -> IncidentRecord:
    """Compatibility helper; prefer ``engine.record_attempt(...)`` in new code.

    ``error_type`` remains accepted for compatibility with earlier callers, while
    the default remains the syntax-specific ``"syntax_error"`` classification.
    """
    if engine is None:
        engine = init_discipline_engine(incident_store_path=incident_store_path)
    return engine.record_attempt(
        incident_id=incident_id,
        task=task,
        file_path=file_path,
        exact_error=exact_error,
        error_type=error_type,
        approach_description=approach_description,
    )


def check_syntax_error_loop(
    file_path: str,
    *,
    engine: ExecutionDisciplineEngine | None = None,
    incident_store_path: str | Path | None = None,
):
    """Compile a Python file and check an existing syntax-error incident loop."""
    if engine is None:
        engine = init_discipline_engine(incident_store_path=incident_store_path)

    try:
        content = Path(file_path).read_text(encoding="utf-8")
        compile(content, file_path, "exec")
    except SyntaxError as exc:
        normalized = normalize_error_message("syntax_error", str(exc))
        return engine.check_and_block("syntax_error", normalized, file_path)
    except OSError:
        pass

    return engine.check_and_block("syntax_error", "syntax_error:generic", file_path)
