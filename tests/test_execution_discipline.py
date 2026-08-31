"""DARWIN ZERO-0 Execution Discipline Protocol tests.

These tests intentionally isolate incident persistence with pytest ``tmp_path``.
They never read, reset, or delete the production runtime incident store.
"""

import json

from core.execution_discipline import (
    ExecutionDisciplineEngine,
    IncidentRecord,
    LOOP_DETECTION_THRESHOLD,
    STATUS_ESCALATED,
    STATUS_RESOLVED,
    init_discipline_engine,
    normalize_error_message,
)


TEST_FILE = "tests/test_capability_registry.py"


def isolated_engine(tmp_path):
    return init_discipline_engine(
        incident_store_path=tmp_path / "execution_discipline_incidents.json"
    )


def record_syntax_attempt(
    engine,
    *,
    incident_id,
    task="fix_syntax_error",
    file_path=TEST_FILE,
    exact_error="closing parenthesis issue",
    approach_description=None,
):
    return engine.record_attempt(
        incident_id=incident_id,
        task=task,
        file_path=file_path,
        exact_error=exact_error,
        error_type="syntax_error",
        approach_description=approach_description,
    )


def test_normalize_syntax_error():
    msg = (
        "closing parenthesis ']' does not match opening parenthesis '{' "
        "on line 650"
    )
    normalized = normalize_error_message("syntax_error", msg)
    assert normalized.startswith("syntax_error:")
    assert "closing parenthesis" in normalized
    assert "opening parenthesis" in normalized
    assert "line 650" not in normalized


def test_normalize_indentation_error():
    normalized = normalize_error_message(
        "indentation", "unexpected indentation on line 10"
    )
    assert normalized.startswith("indentation:")
    assert "line 10" not in normalized


def test_init_engine(tmp_path):
    store = tmp_path / "incidents.json"
    engine = init_discipline_engine(incident_store_path=store)
    assert isinstance(engine, ExecutionDisciplineEngine)
    assert engine.incident_store_path == store
    assert engine.incidents == []
    assert engine._incident_index == {}
    assert not store.exists()


def test_record_attempt(tmp_path):
    engine = isolated_engine(tmp_path)
    exact_error = (
        "closing parenthesis ']' does not match opening parenthesis '{' "
        "on line 650"
    )
    incident = record_syntax_attempt(
        engine,
        incident_id="test_inc_001",
        exact_error=exact_error,
        approach_description="heredoc attempt",
    )

    assert incident.incident_id == "test_inc_001"
    assert incident.task == "fix_syntax_error"
    assert incident.file_path == TEST_FILE
    assert incident.exact_error == exact_error
    assert incident.error_type == "syntax_error"
    assert incident.attempts == 1
    assert len(incident.failed_approaches) == 1
    assert incident.failed_approaches[0]["approach"] == "heredoc attempt"


def test_record_multiple_attempts(tmp_path):
    engine = isolated_engine(tmp_path)
    for approach in ("heredoc v1", "heredoc v2"):
        record_syntax_attempt(
            engine,
            incident_id="test_inc_002",
            approach_description=approach,
        )

    incident = engine._find_incident("test_inc_002")
    assert incident is not None
    assert incident.attempts == 2
    assert [a["approach"] for a in incident.failed_approaches] == [
        "heredoc v1",
        "heredoc v2",
    ]


def test_duplicate_incident_id_cannot_cross_files(tmp_path):
    engine = isolated_engine(tmp_path)
    record_syntax_attempt(engine, incident_id="same_id", file_path="tests/a.py")

    try:
        record_syntax_attempt(engine, incident_id="same_id", file_path="tests/b.py")
        assert False, "Expected ValueError for incident ID reused across files"
    except ValueError as exc:
        assert "already associated" in str(exc)


def test_loop_detection_threshold(tmp_path):
    engine = isolated_engine(tmp_path)
    for i in range(LOOP_DETECTION_THRESHOLD):
        record_syntax_attempt(
            engine,
            incident_id="test_inc_003",
            approach_description=f"bad approach {i + 1}",
        )

    incident = engine._find_incident("test_inc_003")
    assert incident is not None
    assert incident.attempts == LOOP_DETECTION_THRESHOLD

    normalized = normalize_error_message("syntax_error", "closing parenthesis issue")
    should_block, rec, message = engine.check_and_block(
        "syntax_error", normalized, TEST_FILE
    )
    assert should_block is True
    assert rec is incident
    assert "LOOP_DETECTED" in message


def test_loop_detection_not_yet(tmp_path):
    engine = isolated_engine(tmp_path)
    for i in range(LOOP_DETECTION_THRESHOLD - 1):
        record_syntax_attempt(
            engine,
            incident_id="test_inc_004",
            approach_description=f"bad approach {i + 1}",
        )

    normalized = normalize_error_message("syntax_error", "closing parenthesis issue")
    should_block, incident, _ = engine.check_and_block(
        "syntax_error", normalized, TEST_FILE
    )
    assert should_block is False
    assert incident is not None
    assert incident.attempts == LOOP_DETECTION_THRESHOLD - 1


def test_block_source_deletion_requires_owner_approval(tmp_path):
    engine = isolated_engine(tmp_path)

    is_blocked, message = engine.block_source_deletion(TEST_FILE, "test fix")
    assert is_blocked is True
    assert "BLOCKED" in message
    assert "owner approval" in message.lower()

    is_blocked_after_approval, approved_message = engine.block_source_deletion(
        TEST_FILE, "test fix", owner_approved=True
    )
    assert is_blocked_after_approval is False
    assert "OWNER APPROVED" in approved_message


def test_allow_safe_patch_no_loop(tmp_path):
    engine = isolated_engine(tmp_path)
    record_syntax_attempt(engine, incident_id="test_inc_007")
    result = engine.resolve_incident(
        "test_inc_007",
        successful_recovery="minimal bracket patch",
        recovery_pattern="py_compile -> inspect exact lines -> minimal patch",
    )
    assert result is not None

    is_allowed, message = engine.allow_safe_patch(TEST_FILE, "minimal patch")
    assert is_allowed is True
    assert "ALLOWED" in message


def test_allow_safe_patch_with_loop(tmp_path):
    engine = isolated_engine(tmp_path)
    for i in range(LOOP_DETECTION_THRESHOLD):
        record_syntax_attempt(
            engine,
            incident_id="test_inc_008",
            approach_description=f"bad approach {i + 1}",
        )

    is_allowed, message = engine.allow_safe_patch(TEST_FILE, "patch attempt")
    assert is_allowed is False
    assert "BLOCKED" in message


def test_incident_persistence_round_trip(tmp_path):
    store = tmp_path / "execution_discipline_incidents.json"
    engine = init_discipline_engine(incident_store_path=store)

    incident = record_syntax_attempt(
        engine,
        incident_id="test_inc_persist",
        task="test_persistence",
        exact_error="test error",
        approach_description="minimal patch",
    )
    original_detected_at = incident.detected_at

    assert store.exists()
    raw = json.loads(store.read_text(encoding="utf-8"))
    assert raw[0]["incident_id"] == "test_inc_persist"

    fresh_engine = init_discipline_engine(incident_store_path=store)
    loaded = fresh_engine._find_incident("test_inc_persist")
    assert isinstance(loaded, IncidentRecord)
    assert loaded.detected_at == original_detected_at
    assert loaded.attempts == 1
    assert loaded.failed_approaches[0]["approach"] == "minimal patch"


def test_incident_resolution(tmp_path):
    engine = isolated_engine(tmp_path)
    for i in range(LOOP_DETECTION_THRESHOLD):
        record_syntax_attempt(
            engine,
            incident_id="test_inc_resolve",
            exact_error="syntax error",
            approach_description=f"attempt {i + 1}",
        )

    normalized = normalize_error_message("syntax_error", "syntax error")
    blocked_before, _, _ = engine.check_and_block(
        "syntax_error", normalized, TEST_FILE
    )
    assert blocked_before is True

    result = engine.resolve_incident(
        "test_inc_resolve",
        successful_recovery="minimal patch",
        verification_evidence=["targeted pytest PASS", "full pytest PASS"],
    )
    assert result is not None
    assert result.resolution_status == STATUS_RESOLVED
    assert result.resolved_at is not None

    blocked_after, _, _ = engine.check_and_block(
        "syntax_error", normalized, TEST_FILE
    )
    assert blocked_after is False


def test_incident_fail(tmp_path):
    engine = isolated_engine(tmp_path)
    record_syntax_attempt(
        engine,
        incident_id="test_inc_fail",
        exact_error="syntax error",
    )

    result = engine.fail_incident(
        "test_inc_fail", reason="All recovery approaches exhausted"
    )
    assert result is not None
    assert result.resolution_status == STATUS_ESCALATED
    assert "All recovery approaches exhausted" in result.successful_recovery
    assert result.resolved_at is not None


def test_normalization_consistency():
    msg = (
        "closing parenthesis ']' does not match opening parenthesis '{' "
        "on line 650"
    )
    assert (
        normalize_error_message("syntax_error", msg)
        == normalize_error_message("syntax_error", msg)
        == normalize_error_message("syntax_error", msg)
    )


def test_loop_index_integrity(tmp_path):
    engine = isolated_engine(tmp_path)
    record_syntax_attempt(
        engine,
        incident_id="test_idx",
        task="test indexing",
        exact_error="test error",
    )

    key = ("syntax_error", "syntax_error:test error")
    assert key in engine._incident_index
    assert engine._incident_index[key][0].incident_id == "test_idx"


def test_full_discipline_workflow(tmp_path):
    engine = isolated_engine(tmp_path)

    for i in range(LOOP_DETECTION_THRESHOLD):
        record_syntax_attempt(
            engine,
            incident_id="test_full_workflow",
            task="attempt fix",
            approach_description=f"approach {i + 1}",
        )

    incident = engine._find_incident("test_full_workflow")
    assert incident is not None
    assert incident.attempts == LOOP_DETECTION_THRESHOLD

    normalized = normalize_error_message("syntax_error", "closing parenthesis issue")
    should_block, _, _ = engine.check_and_block(
        "syntax_error", normalized, TEST_FILE
    )
    assert should_block is True

    is_allowed, _ = engine.allow_safe_patch(TEST_FILE, "another mutation")
    assert is_allowed is False

    resolution = engine.resolve_incident(
        "test_full_workflow",
        successful_recovery="minimal patch",
        recovery_pattern="evidence -> minimal patch -> targeted test -> full test",
        verification_evidence=["targeted PASS", "full PASS"],
    )
    assert resolution is not None
    assert resolution.resolution_status == STATUS_RESOLVED

    should_block_after, _, _ = engine.check_and_block(
        "syntax_error", normalized, TEST_FILE
    )
    assert should_block_after is False



class _FakeDispatcher:
    def __init__(self):
        self.calls = []

    def _record(self, name, **kwargs):
        self.calls.append((name, kwargs))

    def incident_detected(self, **kwargs):
        self._record("incident_detected", **kwargs)

    def recovery_attempted(self, **kwargs):
        self._record("recovery_attempted", **kwargs)

    def loop_detected(self, **kwargs):
        self._record("loop_detected", **kwargs)

    def owner_escalation_required(self, **kwargs):
        self._record("owner_escalation_required", **kwargs)

    def recovery_succeeded(self, **kwargs):
        self._record("recovery_succeeded", **kwargs)

    def recovery_failed(self, **kwargs):
        self._record("recovery_failed", **kwargs)


def test_loop_and_escalation_events(tmp_path):
    dispatcher = _FakeDispatcher()
    engine = init_discipline_engine(
        event_dispatcher=dispatcher,
        incident_store_path=tmp_path / "events.json",
    )

    for i in range(LOOP_DETECTION_THRESHOLD):
        record_syntax_attempt(
            engine,
            incident_id="event_loop",
            approach_description=f"attempt {i + 1}",
        )

    normalized = normalize_error_message("syntax_error", "closing parenthesis issue")
    should_block, _, _ = engine.check_and_block(
        "syntax_error", normalized, TEST_FILE
    )
    assert should_block is True

    names = [name for name, _ in dispatcher.calls]
    assert "incident_detected" in names
    assert names.count("recovery_attempted") == LOOP_DETECTION_THRESHOLD
    assert "loop_detected" in names
    assert "owner_escalation_required" in names


def test_recovery_lifecycle_events(tmp_path):
    dispatcher = _FakeDispatcher()
    engine = init_discipline_engine(
        event_dispatcher=dispatcher,
        incident_store_path=tmp_path / "events.json",
    )

    record_syntax_attempt(engine, incident_id="event_resolve")
    engine.resolve_incident("event_resolve", successful_recovery="fixed")

    record_syntax_attempt(engine, incident_id="event_fail")
    engine.fail_incident("event_fail", reason="blocked")

    names = [name for name, _ in dispatcher.calls]
    assert "recovery_succeeded" in names
    assert "recovery_failed" in names
    assert "owner_escalation_required" in names


def test_foundational_tests_still_pass():
    """Regression bridge: the existing foundational suite must remain green."""
    from tests.test_foundational import run_all_tests

    assert run_all_tests() is True
