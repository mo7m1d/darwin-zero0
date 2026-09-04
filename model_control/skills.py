from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path


class SkillDenied(RuntimeError):
    pass


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


@dataclass(frozen=True)
class IntegrationCandidate:
    integration_id: str
    kind: str
    source: str
    immutable_version: str
    source_hash: str
    author: str
    requested_capabilities: tuple[str, ...] = ()
    tools_exposed: tuple[str, ...] = ()
    hooks: tuple[str, ...] = ()
    network_needs: bool = False
    filesystem_needs: bool = False
    subprocess_needs: bool = False
    secret_needs: bool = False
    external_effects: bool = False
    paid_dependency: bool = False
    license_id: str = "UNKNOWN"

    def validate(self):
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,127}", self.integration_id):
            raise SkillDenied("invalid integration id")
        if self.kind not in {"skill", "mcp", "plugin", "orchestrator"}:
            raise SkillDenied("invalid integration kind")
        if not self.source or not self.author or not self.immutable_version:
            raise SkillDenied("missing provenance")
        if "latest" in self.immutable_version.casefold() or not re.fullmatch(r"[0-9a-f]{64}", self.source_hash):
            raise SkillDenied("unpinned integration source")
        return self


class SkillEvaluator:
    PATTERNS = {
        "dangerous_shell": r"(?i)(rm\s+-rf|Remove-Item\s+.*-Recurse|format\s+[a-z]:)",
        "secret_access": r"(?i)(\.env|api[_-]?key|password|private[_-]?key|access[_-]?token)",
        "network": r"(?i)(requests\.|urllib\.|fetch\(|curl\b|Invoke-WebRequest)",
        "subprocess": r"(?i)(subprocess\.|os\.system|Start-Process|nohup|child_process)",
        "control_mutation": r"(?i)(budget\.sqlite|integration[_-]registry|model[_-]registry|pricing[_-]registry|skill[_-]registry|prompt[_-]cache|darwin-tool-policy|owner_approval|context\.sqlite|checkpoint-ledger)",
        "instruction_override": r"(?i)(ignore previous instructions|override safety|you are now|bypass approval)",
        "self_modification": r"(?i)(__file__.*write|open\(__file__.*[wa])",
        "unpinned_dependency": r"(?i)(pip install\s+[a-z0-9_.-]+\s*(?:$|[;&])|npm install\s+[a-z0-9@/_.-]+\s*(?:$|[;&]))",
    }

    def static_scan(self, code: str) -> dict:
        findings = sorted(name for name, pattern in self.PATTERNS.items() if re.search(pattern, code))
        return {"passed": not findings, "findings": findings,
                "code_hash": hashlib.sha256(code.encode()).hexdigest()}

    def evaluate(self, candidate: IntegrationCandidate, code: str, dynamic_passed: bool,
                 security_passed: bool, benchmark_passed: int, benchmark_total: int,
                 dynamic_evidence_hash: str = "", security_evidence_hash: str = "",
                 benchmark_fixture_hash: str = "") -> dict:
        candidate.validate()
        scan = self.static_scan(code)
        if hashlib.sha256(code.encode()).hexdigest() != candidate.source_hash:
            raise SkillDenied("source changed after registration")
        if benchmark_total <= 0 or benchmark_passed < 0 or benchmark_passed > benchmark_total:
            raise SkillDenied("invalid benchmark")
        for evidence_hash in (dynamic_evidence_hash, security_evidence_hash, benchmark_fixture_hash):
            if not re.fullmatch(r"[0-9a-f]{64}", evidence_hash):
                raise SkillDenied("evaluation provenance required")
        cost_ok = not candidate.paid_dependency
        passed = scan["passed"] and dynamic_passed and security_passed and cost_ok and benchmark_passed == benchmark_total
        return {"schema": "darwin.skill-evaluation.v1", "source_hash": candidate.source_hash,
                "static": scan, "dynamic_passed": bool(dynamic_passed),
                "security_passed": bool(security_passed), "cost_passed": cost_ok,
                "benchmark": {"passed": benchmark_passed, "total": benchmark_total},
                "provenance": {"dynamic": dynamic_evidence_hash, "security": security_evidence_hash,
                               "benchmark_fixture": benchmark_fixture_hash},
                "claims_are_evidence": False, "verdict": "PASS" if passed else "FAIL"}


class SkillRegistry:
    """Default-deny evaluated registry extending Integration Registry policy."""
    def __init__(self, database: Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
CREATE TABLE IF NOT EXISTS integrations(
 integration_id TEXT PRIMARY KEY,kind TEXT NOT NULL,source TEXT NOT NULL,immutable_version TEXT NOT NULL,
 source_hash TEXT NOT NULL,metadata_json TEXT NOT NULL,status TEXT NOT NULL,evaluation_json TEXT,
 acceptance_ref TEXT,acceptance_hash TEXT,activated INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS tools(tool_name TEXT NOT NULL,integration_id TEXT NOT NULL REFERENCES integrations(integration_id),PRIMARY KEY(tool_name,integration_id));
CREATE TABLE IF NOT EXISTS hooks(hook_name TEXT NOT NULL,integration_id TEXT NOT NULL REFERENCES integrations(integration_id),PRIMARY KEY(hook_name,integration_id));
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,integration_id TEXT,event_type TEXT NOT NULL,payload_json TEXT NOT NULL,previous_hash TEXT NOT NULL,event_hash TEXT NOT NULL);
""")

    def connect(self):
        db = sqlite3.connect(self.database, timeout=30, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _event(self, db, integration_id, event_type, payload):
        previous = db.execute("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        prior = previous[0] if previous else "0" * 64
        body = json.dumps({"integration_id": integration_id, "event_type": event_type,
                           "payload": payload}, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256((prior + body).encode()).hexdigest()
        db.execute("INSERT INTO events(integration_id,event_type,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)",
                   (integration_id, event_type, json.dumps(payload, sort_keys=True, separators=(",", ":")), prior, digest))

    def register(self, candidate: IntegrationCandidate):
        candidate.validate()
        metadata = asdict(candidate)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM integrations WHERE integration_id=?", (candidate.integration_id,)).fetchone():
                raise SkillDenied("duplicate integration")
            conflicts = []
            for tool in candidate.tools_exposed:
                conflicts += [row[0] for row in db.execute("SELECT integration_id FROM tools WHERE tool_name=?", (tool,))]
            for hook in candidate.hooks:
                conflicts += [row[0] for row in db.execute("SELECT integration_id FROM hooks WHERE hook_name=?", (hook,))]
            status = "QUARANTINED" if conflicts else "CANDIDATE"
            db.execute("INSERT INTO integrations VALUES(?,?,?,?,?,? ,?,NULL,NULL,NULL,0)",
                       (candidate.integration_id, candidate.kind, candidate.source, candidate.immutable_version,
                        candidate.source_hash, json.dumps(metadata, sort_keys=True), status))
            db.executemany("INSERT INTO tools VALUES(?,?)", [(tool, candidate.integration_id) for tool in candidate.tools_exposed])
            db.executemany("INSERT INTO hooks VALUES(?,?)", [(hook, candidate.integration_id) for hook in candidate.hooks])
            self._event(db, candidate.integration_id, "REGISTERED", {"status": status, "conflicts": sorted(set(conflicts))})
            db.commit()
        return status

    def record_evaluation(self, integration_id: str, result: dict):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM integrations WHERE integration_id=?", (integration_id,)).fetchone()
            if not row or row[0] != "CANDIDATE":
                raise SkillDenied("integration unavailable for evaluation")
            provenance = result.get("provenance", {}) if isinstance(result, dict) else {}
            if result.get("schema") != "darwin.skill-evaluation.v1" or any(
                not re.fullmatch(r"[0-9a-f]{64}", provenance.get(name, ""))
                for name in ("dynamic", "security", "benchmark_fixture")
            ):
                raise SkillDenied("evaluation evidence invalid")
            source_hash = db.execute("SELECT source_hash FROM integrations WHERE integration_id=?", (integration_id,)).fetchone()[0]
            if result.get("source_hash") != source_hash or result.get("static", {}).get("code_hash") != source_hash:
                raise SkillDenied("evaluation source mismatch")
            status = "EVALUATED" if result.get("verdict") == "PASS" else "REJECTED"
            db.execute("UPDATE integrations SET status=?,evaluation_json=? WHERE integration_id=?",
                       (status, json.dumps(result, sort_keys=True), integration_id))
            self._event(db, integration_id, "EVALUATED", {"status": status, "result_hash": hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()})
            db.commit()

    def accept(self, integration_id: str, owner_authorized: bool, acceptance_ref: str, acceptance_hash: str):
        if not owner_authorized or not acceptance_ref or not re.fullmatch(r"[0-9a-f]{64}", acceptance_hash):
            raise SkillDenied("Owner and Acceptance evidence required")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM integrations WHERE integration_id=?", (integration_id,)).fetchone()
            if not row or row[0] != "EVALUATED":
                raise SkillDenied("integration not evaluated")
            db.execute("UPDATE integrations SET status='ACCEPTED',acceptance_ref=?,acceptance_hash=? WHERE integration_id=?",
                       (acceptance_ref, acceptance_hash, integration_id))
            self._event(db, integration_id, "ACCEPTED", {"acceptance_ref": acceptance_ref, "acceptance_hash": acceptance_hash})
            db.commit()

    def activate(self, integration_id: str, actual_source_hash: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM integrations WHERE integration_id=?", (integration_id,)).fetchone()
            if not row or row["status"] != "ACCEPTED" or row["source_hash"] != actual_source_hash:
                raise SkillDenied("activation denied")
            db.execute("UPDATE integrations SET activated=1 WHERE integration_id=?", (integration_id,))
            self._event(db, integration_id, "ACTIVATED", {})
            db.commit()
            return dict(row)

    def verify_ledger(self) -> bool:
        previous = "0" * 64
        with self.connect() as db:
            for row in db.execute("SELECT * FROM events ORDER BY seq"):
                payload = json.loads(row["payload_json"])
                body = json.dumps({"integration_id": row["integration_id"], "event_type": row["event_type"],
                                   "payload": payload}, sort_keys=True, separators=(",", ":"))
                if row["previous_hash"] != previous or hashlib.sha256((previous + body).encode()).hexdigest() != row["event_hash"]:
                    return False
                previous = row["event_hash"]
        return True

    def status(self, integration_id: str) -> str:
        with self.connect() as db:
            row = db.execute("SELECT status FROM integrations WHERE integration_id=?", (integration_id,)).fetchone()
            return row[0] if row else "DENIED"
