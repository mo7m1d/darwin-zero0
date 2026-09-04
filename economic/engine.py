from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import replace
from pathlib import Path

from .model import EconomicAmounts, Opportunity, OpportunityState, canonical
from .registry import CapabilityRegistry


class EconomicDenied(RuntimeError):
    pass


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


TRANSITIONS = {
    "DISCOVERED": {"RESEARCHED", "REJECTED", "FAILED", "BLOCKED"},
    "RESEARCHED": {"POLICY_CHECKED", "REJECTED", "FAILED", "BLOCKED"},
    "POLICY_CHECKED": {"SCORED", "REJECTED", "FAILED", "BLOCKED"},
    "SCORED": {"CANDIDATE", "REJECTED", "FAILED", "BLOCKED"},
    "CANDIDATE": {"OWNER_DECISION", "DRY_RUN_READY", "REJECTED", "FAILED", "BLOCKED"},
    "OWNER_DECISION": {"DRY_RUN_READY", "REJECTED", "FAILED", "BLOCKED"},
    "DRY_RUN_READY": {"EXECUTION_READY", "REJECTED", "FAILED", "BLOCKED"},
    "EXECUTION_READY": {"EXECUTING", "REJECTED", "FAILED", "BLOCKED"},
    "EXECUTING": {"ACCEPTANCE_PENDING", "FAILED", "BLOCKED"},
    "ACCEPTANCE_PENDING": {"ACCEPTED", "REJECTED", "FAILED", "BLOCKED"},
    "ACCEPTED": set(), "REJECTED": set(), "FAILED": set(), "BLOCKED": set(),
}


class EconomicStore:
    def __init__(self, path: Path, now=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.now = now or (lambda: int(time.time()))
        with self.connect() as db:
            db.executescript("""
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS opportunities(
 opportunity_id TEXT PRIMARY KEY,family_id TEXT NOT NULL,title TEXT NOT NULL,state TEXT NOT NULL,
 platform_id TEXT,payload_json TEXT NOT NULL,fingerprint TEXT NOT NULL,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS events(
 seq INTEGER PRIMARY KEY AUTOINCREMENT,opportunity_id TEXT NOT NULL,event_type TEXT NOT NULL,
 payload_json TEXT NOT NULL,created_at INTEGER NOT NULL,previous_hash TEXT NOT NULL,event_hash TEXT NOT NULL);
""")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        return db

    def _event(self, db, opportunity_id, event_type, payload):
        row = db.execute("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        previous = row[0] if row else "0" * 64
        created = self.now()
        body = canonical({"opportunity_id": opportunity_id, "event_type": event_type,
                          "payload": payload, "created_at": created})
        digest = hashlib.sha256((previous + body).encode()).hexdigest()
        db.execute("INSERT INTO events(opportunity_id,event_type,payload_json,created_at,previous_hash,event_hash) VALUES(?,?,?,?,?,?)",
                   (opportunity_id, event_type, canonical(payload), created, previous, digest))

    def put(self, opportunity: Opportunity, event_type="CREATED"):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM opportunities WHERE opportunity_id=?", (opportunity.opportunity_id,)).fetchone():
                raise EconomicDenied("opportunity id already exists")
            now = self.now()
            db.execute("INSERT INTO opportunities VALUES(?,?,?,?,?,?,?,?,?)",
                       (opportunity.opportunity_id, opportunity.family_id, opportunity.title,
                        opportunity.state.value, opportunity.platform_id, canonical(opportunity.payload()),
                        opportunity.fingerprint, now, now))
            self._event(db, opportunity.opportunity_id, event_type, {"fingerprint": opportunity.fingerprint})

    def update(self, opportunity: Opportunity, expected_fingerprint: str, event_type: str, evidence: dict):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT fingerprint FROM opportunities WHERE opportunity_id=?", (opportunity.opportunity_id,)).fetchone()
            if not row or row[0] != expected_fingerprint:
                raise EconomicDenied("stale or missing opportunity")
            db.execute("UPDATE opportunities SET state=?,payload_json=?,fingerprint=?,updated_at=? WHERE opportunity_id=?",
                       (opportunity.state.value, canonical(opportunity.payload()), opportunity.fingerprint,
                        self.now(), opportunity.opportunity_id))
            self._event(db, opportunity.opportunity_id, event_type, evidence)

    def get(self, opportunity_id: str) -> Opportunity:
        with self.connect() as db:
            row = db.execute("SELECT payload_json FROM opportunities WHERE opportunity_id=?", (opportunity_id,)).fetchone()
        if not row:
            raise EconomicDenied("opportunity not found")
        payload = json.loads(row[0])
        raw = {key: payload["amounts"][key] for key in EconomicAmounts.__dataclass_fields__}
        return Opportunity(opportunity_id=payload["opportunity_id"], family_id=payload["family_id"],
                           title=payload["title"], amounts=EconomicAmounts(**raw),
                           state=OpportunityState(payload["state"]), platform_id=payload["platform_id"],
                           evidence_refs=tuple(payload["evidence_refs"]), policy_passed=payload["policy_passed"],
                           dry_run_passed=payload["dry_run_passed"],
                           owner_capital_authorized=payload["owner_capital_authorized"],
                           capital_components_cents=payload["capital_components_cents"])

    def list(self) -> list[Opportunity]:
        with self.connect() as db:
            ids = [row[0] for row in db.execute("SELECT opportunity_id FROM opportunities")]
        return [self.get(item) for item in ids]

    def verify_ledger(self) -> bool:
        previous = "0" * 64
        with self.connect() as db:
            rows = db.execute("SELECT * FROM events ORDER BY seq").fetchall()
        for row in rows:
            body = canonical({"opportunity_id": row["opportunity_id"], "event_type": row["event_type"],
                              "payload": json.loads(row["payload_json"]), "created_at": row["created_at"]})
            expected = hashlib.sha256((previous + body).encode()).hexdigest()
            if row["previous_hash"] != previous or row["event_hash"] != expected:
                return False
            previous = expected
        return True


class EconomicEngine:
    def __init__(self, registry: CapabilityRegistry, store: EconomicStore):
        self.registry = registry
        self.store = store

    def add(self, opportunity: Opportunity):
        self.registry.get(opportunity.family_id)
        self.store.put(opportunity)
        return opportunity

    def transition(self, opportunity_id: str, target: OpportunityState, *, actor: str,
                   evidence_ref: str = "", owner_authorized: bool = False,
                   owner_approval_ref: str = "", owner_approval_hash: str = "",
                   acceptance_verified: bool = False, acceptance_hash: str = "") -> Opportunity:
        current = self.store.get(opportunity_id)
        if target.value not in TRANSITIONS[current.state.value]:
            raise EconomicDenied("invalid opportunity transition")
        if target in {OpportunityState.POLICY_CHECKED, OpportunityState.SCORED,
                      OpportunityState.CANDIDATE} and not evidence_ref:
            raise EconomicDenied("evidence required")
        if target == OpportunityState.EXECUTION_READY:
            if not current.policy_passed or not current.dry_run_passed:
                raise EconomicDenied("policy and dry-run gates required")
            if current.amounts.capital_required_cents > 0 and not valid_owner_authorization(
                    actor, owner_authorized, owner_approval_ref, owner_approval_hash):
                raise EconomicDenied("Owner capital authorization required")
        if target == OpportunityState.EXECUTING and not valid_owner_authorization(
                actor, owner_authorized, owner_approval_ref, owner_approval_hash):
            raise EconomicDenied("Owner authorization required for external execution")
        if target == OpportunityState.ACCEPTED:
            if actor != "acceptance_gate" or not acceptance_verified or not evidence_ref or not full_hash(acceptance_hash):
                raise EconomicDenied("Acceptance Gate evidence required")
        updates = {"state": target}
        if target == OpportunityState.POLICY_CHECKED:
            updates["policy_passed"] = True
        if target == OpportunityState.DRY_RUN_READY:
            updates["dry_run_passed"] = True
        if owner_authorized and current.amounts.capital_required_cents > 0:
            updates["owner_capital_authorized"] = True
        if evidence_ref:
            updates["evidence_refs"] = current.evidence_refs + (evidence_ref,)
        changed = replace(current, **updates)
        self.store.update(changed, current.fingerprint, f"STATE_{target.value}",
                          {"actor": actor, "evidence_ref": evidence_ref,
                           "owner_authorized": bool(owner_authorized),
                           "owner_approval_ref": owner_approval_ref,
                           "owner_approval_hash": owner_approval_hash,
                           "acceptance_verified": bool(acceptance_verified),
                           "acceptance_hash": acceptance_hash})
        return changed

    def rank(self, states=(OpportunityState.SCORED, OpportunityState.CANDIDATE)) -> list[Opportunity]:
        allowed = set(states)
        return sorted((item for item in self.store.list() if item.state in allowed), key=lambda item: item.rank_key)


def full_hash(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def valid_owner_authorization(actor: str, authorized: bool, reference: str, digest: str) -> bool:
    return actor == "owner" and authorized is True and bool(reference) and full_hash(digest)
