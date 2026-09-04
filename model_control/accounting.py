from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .registry import ModelRegistry, integer
from .router import charge


class CostDenied(RuntimeError):
    pass


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0

    def validate(self) -> "Usage":
        for name, value in self.__dict__.items():
            integer(value, name)
        if self.cached_input_tokens > self.input_tokens:
            raise CostDenied("cached tokens exceed input")
        return self


@dataclass(frozen=True)
class RunBinding:
    run_id: str
    task_fingerprint: str
    nonce: str
    signature: str


@dataclass(frozen=True)
class UsageEvidence:
    request_id: str
    provider_id: str
    response_model: str
    provider_request_id: str
    usage: Usage
    signature: str


class TrustedUsageAttestor:
    """Adapter-side signer for provider response metadata; never model supplied."""
    def __init__(self, control_key: bytes | None = None):
        self._key = control_key or secrets.token_bytes(32)

    @staticmethod
    def _body(request_id, provider_id, response_model, provider_request_id, usage):
        return json.dumps({"request_id": request_id, "provider_id": provider_id,
                           "response_model": response_model, "provider_request_id": provider_request_id,
                           "usage": usage.__dict__}, sort_keys=True, separators=(",", ":")).encode()

    def attest(self, request_id: str, provider_id: str, response_model: str,
               provider_request_id: str, usage: Usage) -> UsageEvidence:
        usage.validate()
        signature = hmac.new(self._key, self._body(request_id, provider_id, response_model,
                                                   provider_request_id, usage), hashlib.sha256).hexdigest()
        return UsageEvidence(request_id, provider_id, response_model, provider_request_id, usage, signature)

    def verify(self, evidence: UsageEvidence) -> bool:
        if not isinstance(evidence, UsageEvidence):
            return False
        expected = hmac.new(self._key, self._body(evidence.request_id, evidence.provider_id,
                                                  evidence.response_model, evidence.provider_request_id,
                                                  evidence.usage), hashlib.sha256).hexdigest()
        return hmac.compare_digest(evidence.signature, expected)


class TrustedRunBinder:
    """Issues opaque bindings from trusted orchestration, never model arguments."""
    def __init__(self, control_key: bytes | None = None):
        self._key = control_key or secrets.token_bytes(32)

    def bind(self, budget_store, run_id: str, task_fingerprint: str) -> RunBinding:
        status = budget_store.status(run_id)
        if status["task_fingerprint"] != task_fingerprint or status["state"] != "RUNNING":
            raise CostDenied("trusted run identity mismatch")
        nonce = secrets.token_hex(16)
        body = f"{run_id}\0{task_fingerprint}\0{nonce}".encode()
        return RunBinding(run_id, task_fingerprint, nonce, hmac.new(self._key, body, hashlib.sha256).hexdigest())

    def verify(self, binding: RunBinding) -> bool:
        if not isinstance(binding, RunBinding):
            return False
        body = f"{binding.run_id}\0{binding.task_fingerprint}\0{binding.nonce}".encode()
        expected = hmac.new(self._key, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(binding.signature, expected)


class CostController:
    """Durable exact-micros accounting for calls made through this boundary."""
    def __init__(self, database: Path, budget_store, registry: ModelRegistry,
                 binder: TrustedRunBinder, usage_attestor: TrustedUsageAttestor, now=None):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.budget_store = budget_store
        self.registry = registry
        self.binder = binder
        self.usage_attestor = usage_attestor
        self.now = now or (lambda: int(time.time()))
        self._initialize()

    def connect(self):
        db = sqlite3.connect(self.database, timeout=30, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _initialize(self):
        with self.connect() as db:
            db.executescript("""
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS calls(
 request_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,task_fingerprint TEXT NOT NULL,
 provider_id TEXT NOT NULL,model_id TEXT NOT NULL,upstream_model TEXT NOT NULL,
 pricing_version TEXT NOT NULL,reserved_micros INTEGER NOT NULL CHECK(reserved_micros>=0),
 charged_micros INTEGER CHECK(charged_micros>=0),state TEXT NOT NULL,
 input_tokens INTEGER,output_tokens INTEGER,cached_input_tokens INTEGER,cache_write_tokens INTEGER,
 created_at INTEGER NOT NULL,reconciled_at INTEGER);
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,request_id TEXT,event_type TEXT NOT NULL,
 payload_json TEXT NOT NULL,created_at INTEGER NOT NULL,previous_hash TEXT NOT NULL,event_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS control(singleton INTEGER PRIMARY KEY CHECK(singleton=1),fail_closed INTEGER NOT NULL);
INSERT OR IGNORE INTO control VALUES(1,0);
""")

    def _event(self, db, request_id, event_type, payload):
        previous = db.execute("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        previous_hash = previous[0] if previous else "0" * 64
        created = self.now()
        body = json.dumps({"request_id": request_id, "event_type": event_type,
                           "payload": payload, "created_at": created}, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256((previous_hash + body).encode()).hexdigest()
        db.execute("INSERT INTO events(request_id,event_type,payload_json,created_at,previous_hash,event_hash) VALUES(?,?,?,?,?,?)",
                   (request_id, event_type, json.dumps(payload, sort_keys=True, separators=(",", ":")), created, previous_hash, digest))

    def _binding(self, binding):
        if not self.binder.verify(binding):
            raise CostDenied("untrusted run binding")
        status = self.budget_store.status(binding.run_id)
        if status["state"] != "RUNNING" or status["task_fingerprint"] != binding.task_fingerprint:
            raise CostDenied("run unavailable")

    def begin(self, binding: RunBinding, request_id: str, model_identity: str,
              max_input_tokens: int, max_output_tokens: int, owner_spend_authorized: bool = False) -> dict:
        self._binding(binding)
        if not request_id or len(request_id) > 200:
            raise CostDenied("invalid request id")
        max_input_tokens = integer(max_input_tokens, "max_input_tokens")
        max_output_tokens = integer(max_output_tokens, "max_output_tokens")
        model = self.registry.resolve(model_identity)
        if model.status != "ACCEPTED" or not model.owner_approved or not model.enabled:
            raise CostDenied("model not accepted")
        if model.price_class == "unknown":
            raise CostDenied("unknown pricing")
        reserved = charge(max_input_tokens, model.input_micros_per_million or 0) + charge(
            max_output_tokens, model.output_micros_per_million or 0)
        if reserved and not owner_spend_authorized:
            raise CostDenied("OWNER_DECISION")
        with self.connect() as db:
            if db.execute("SELECT fail_closed FROM control WHERE singleton=1").fetchone()[0]:
                raise CostDenied("accounting fail closed")
            unresolved = db.execute("SELECT 1 FROM calls WHERE run_id=? AND state='DISPATCHED' LIMIT 1", (binding.run_id,)).fetchone()
            if unresolved and reserved:
                raise CostDenied("ambiguous prior paid call")
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM calls WHERE request_id=?", (request_id,)).fetchone():
                raise CostDenied("duplicate request id")
            if reserved:
                cents = (reserved + 9_999) // 10_000
                self.budget_store.reserve(binding.run_id, {"spend_cents": cents})
            db.execute("INSERT INTO calls VALUES(?,?,?,?,?,?,?,?,?,'RESERVED',NULL,NULL,NULL,NULL,?,NULL)",
                       (request_id, binding.run_id, binding.task_fingerprint, model.provider_id,
                        model.model_id, model.upstream_model, model.pricing_version, reserved, None, self.now()))
            self._event(db, request_id, "RESERVED", {"reserved_micros": reserved, "pricing_version": model.pricing_version})
            db.commit()
        return {"request_id": request_id, "provider_id": model.provider_id,
                "model_id": model.model_id, "upstream_model": model.upstream_model,
                "reserved_micros": reserved}

    def mark_dispatched(self, request_id: str):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM calls WHERE request_id=?", (request_id,)).fetchone()
            if not row or row[0] != "RESERVED":
                raise CostDenied("call not reservable")
            db.execute("UPDATE calls SET state='DISPATCHED' WHERE request_id=?", (request_id,))
            self._event(db, request_id, "DISPATCHED", {})
            db.commit()

    def abort_before_dispatch(self, request_id: str):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM calls WHERE request_id=?", (request_id,)).fetchone()
            if not row or row[0] != "RESERVED":
                raise CostDenied("cannot abort")
            db.execute("UPDATE calls SET state='ABORTED' WHERE request_id=?", (request_id,))
            self._event(db, request_id, "ABORTED_NO_REFUND", {})
            db.commit()

    def reconcile(self, request_id: str, evidence: UsageEvidence | None) -> int:
        if evidence is None:
            with self.connect() as db:
                db.execute("UPDATE calls SET state='AMBIGUOUS' WHERE request_id=? AND state='DISPATCHED'", (request_id,))
                db.execute("UPDATE control SET fail_closed=1 WHERE singleton=1")
                self._event(db, request_id, "MISSING_USAGE_FAIL_CLOSED", {})
                db.commit()
            raise CostDenied("authoritative usage missing")
        if not self.usage_attestor.verify(evidence) or evidence.request_id != request_id:
            with self.connect() as db:
                db.execute("UPDATE calls SET state='AMBIGUOUS' WHERE request_id=? AND state='DISPATCHED'", (request_id,))
                db.execute("UPDATE control SET fail_closed=1 WHERE singleton=1")
                self._event(db, request_id, "FORGED_USAGE_FAIL_CLOSED", {})
                db.commit()
            raise CostDenied("forged usage evidence")
        usage = evidence.usage
        try:
            usage.validate()
        except Exception:
            with self.connect() as db:
                db.execute("UPDATE calls SET state='AMBIGUOUS' WHERE request_id=? AND state='DISPATCHED'", (request_id,))
                db.execute("UPDATE control SET fail_closed=1 WHERE singleton=1")
                self._event(db, request_id, "INVALID_USAGE_FAIL_CLOSED", {})
                db.commit()
            raise CostDenied("invalid authoritative usage")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM calls WHERE request_id=?", (request_id,)).fetchone()
            if not row or row["state"] != "DISPATCHED":
                raise CostDenied("call not dispatched")
            model = self.registry.resolve(row["model_id"])
            if evidence.provider_id != row["provider_id"] or evidence.response_model != row["upstream_model"]:
                db.execute("UPDATE calls SET state='AMBIGUOUS' WHERE request_id=?", (request_id,))
                db.execute("UPDATE control SET fail_closed=1 WHERE singleton=1")
                self._event(db, request_id, "MODEL_IDENTITY_DRIFT", {"response_model": evidence.response_model})
                db.commit()
                raise CostDenied("provider model identity drift")
            uncached = usage.input_tokens - usage.cached_input_tokens
            actual = charge(uncached, model.input_micros_per_million or 0)
            actual += charge(usage.cached_input_tokens, model.cache_read_micros_per_million or 0)
            actual += charge(usage.cache_write_tokens, model.cache_write_micros_per_million or 0)
            actual += charge(usage.output_tokens, model.output_micros_per_million or 0)
            if actual > row["reserved_micros"]:
                db.execute("UPDATE calls SET state='AMBIGUOUS' WHERE request_id=?", (request_id,))
                db.execute("UPDATE control SET fail_closed=1 WHERE singleton=1")
                self._event(db, request_id, "RESERVATION_EXCEEDED", {"actual_micros": actual})
                db.commit()
                raise CostDenied("usage exceeded reservation")
            db.execute("UPDATE calls SET state='RECONCILED',charged_micros=?,input_tokens=?,output_tokens=?,cached_input_tokens=?,cache_write_tokens=?,reconciled_at=? WHERE request_id=?",
                       (actual, usage.input_tokens, usage.output_tokens, usage.cached_input_tokens,
                        usage.cache_write_tokens, self.now(), request_id))
            self._event(db, request_id, "RECONCILED", {"charged_micros": actual,
                        "provider_request_id": evidence.provider_request_id or "UNAVAILABLE"})
            db.commit()
            return actual

    def verify_ledger(self) -> bool:
        previous = "0" * 64
        with self.connect() as db:
            for row in db.execute("SELECT * FROM events ORDER BY seq"):
                payload = json.loads(row["payload_json"])
                body = json.dumps({"request_id": row["request_id"], "event_type": row["event_type"],
                                   "payload": payload, "created_at": row["created_at"]}, sort_keys=True, separators=(",", ":"))
                if row["previous_hash"] != previous or hashlib.sha256((previous + body).encode()).hexdigest() != row["event_hash"]:
                    return False
                previous = row["event_hash"]
        return True

    def status(self, request_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM calls WHERE request_id=?", (request_id,)).fetchone()
            if not row:
                raise CostDenied("unknown request")
            return dict(row)
