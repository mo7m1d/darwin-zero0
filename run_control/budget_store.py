from __future__ import annotations
import hashlib, json, sqlite3, time
from contextlib import contextmanager
from pathlib import Path

STATES = {"RUNNING","PAUSED","EXHAUSTED","KILLED","FROZEN","COMPLETED","FAILED"}
TERMINAL = {"KILLED","COMPLETED","FAILED"}
DIMENSIONS = ("tool_calls_total","mutation_tool_calls","network_tool_calls",
 "external_effect_actions","recovery_attempts","candidate_rebuilds",
 "wall_clock_seconds","child_runs","spend_cents")
MAX_INT = 2**63 - 1

class BudgetError(RuntimeError): pass
class BudgetDenied(BudgetError): pass

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try: return super().__exit__(*args)
        finally: self.close()

def integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > MAX_INT:
        raise BudgetError(f"invalid {name}")
    return value

class BudgetStore:
    def __init__(self, path, clock=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock or time.time
        self._initialize()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _initialize(self):
        with self.connect() as db:
            db.executescript("""
CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY,parent_run_id TEXT REFERENCES runs(run_id),task_fingerprint TEXT NOT NULL,state TEXT NOT NULL,created_at INTEGER NOT NULL,started_at INTEGER NOT NULL,last_activity_at INTEGER NOT NULL,last_clock INTEGER NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS root_task_identity ON runs(task_fingerprint) WHERE parent_run_id IS NULL;
CREATE TABLE IF NOT EXISTS budgets(run_id TEXT NOT NULL REFERENCES runs(run_id),dimension TEXT NOT NULL,limit_value INTEGER NOT NULL CHECK(limit_value>=0),consumed INTEGER NOT NULL DEFAULT 0 CHECK(consumed>=0),PRIMARY KEY(run_id,dimension));
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,event_type TEXT NOT NULL,payload_json TEXT NOT NULL,previous_hash TEXT NOT NULL,event_hash TEXT NOT NULL UNIQUE,created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS overrides(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,dimension TEXT NOT NULL,old_limit INTEGER NOT NULL,new_limit INTEGER NOT NULL,provenance TEXT NOT NULL,event_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS control(singleton INTEGER PRIMARY KEY CHECK(singleton=1),frozen INTEGER NOT NULL CHECK(frozen IN(0,1)),updated_at INTEGER NOT NULL);
INSERT OR IGNORE INTO control VALUES(1,0,0);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append-only events'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'append-only events'); END;
CREATE TRIGGER IF NOT EXISTS overrides_no_update BEFORE UPDATE ON overrides BEGIN SELECT RAISE(ABORT,'append-only overrides'); END;
CREATE TRIGGER IF NOT EXISTS overrides_no_delete BEFORE DELETE ON overrides BEGIN SELECT RAISE(ABORT,'append-only overrides'); END;
""")

    def now(self): return integer(int(self.clock()), "clock")

    def event(self, db, run_id, kind, payload, now):
        row = db.execute("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        previous = row[0] if row else "0" * 64
        body = json.dumps({"run_id":run_id,"event_type":kind,"payload":payload,"created_at":now}, sort_keys=True, separators=(",",":"))
        digest = hashlib.sha256((previous + body).encode()).hexdigest()
        db.execute("INSERT INTO events(run_id,event_type,payload_json,previous_hash,event_hash,created_at) VALUES(?,?,?,?,?,?)", (run_id,kind,json.dumps(payload,sort_keys=True,separators=(",",":")),previous,digest,now))
        return digest

    def create_run(self, run_id, fingerprint, limits, parent_run_id=None):
        if not run_id or not fingerprint: raise BudgetError("run identity required")
        values = {dimension: 0 for dimension in DIMENSIONS}
        for dimension, value in limits.items():
            if dimension not in DIMENSIONS: raise BudgetError("unknown dimension")
            values[dimension] = integer(value, "limit")
        now = self.now()
        with self.transaction() as db:
            if db.execute("SELECT frozen FROM control WHERE singleton=1").fetchone()[0]: raise BudgetDenied("system frozen")
            if db.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone(): raise BudgetDenied("run id reused")
            if parent_run_id:
                parent = db.execute("SELECT state FROM runs WHERE run_id=?", (parent_run_id,)).fetchone()
                if not parent or parent[0] != "RUNNING": raise BudgetDenied("invalid parent")
                for dimension, value in values.items():
                    budget = db.execute("SELECT limit_value,consumed FROM budgets WHERE run_id=? AND dimension=?", (parent_run_id,dimension)).fetchone()
                    if value > budget[0] - budget[1]: raise BudgetDenied("child exceeds parent envelope")
                self._consume(db, parent_run_id, {"child_runs":1}, now)
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)", (run_id,parent_run_id,fingerprint,"RUNNING",now,now,now,now))
            db.executemany("INSERT INTO budgets VALUES(?,?,?,0)", [(run_id,d,values[d]) for d in DIMENSIONS])
            self.event(db, run_id, "RUN_CREATED", {"parent_run_id":parent_run_id,"fingerprint":fingerprint,"limits":values}, now)

    def ancestry(self, db, run_id):
        result, seen, current = [], set(), run_id
        while current:
            if current in seen: raise BudgetDenied("parent cycle")
            seen.add(current)
            row = db.execute("SELECT run_id,parent_run_id,state,started_at,last_clock FROM runs WHERE run_id=?", (current,)).fetchone()
            if not row: raise BudgetDenied("unknown run")
            result.append(row); current = row["parent_run_id"]
        return result

    def _clock(self, db, row, now):
        if now < row["last_clock"]:
            db.execute("UPDATE runs SET state='EXHAUSTED' WHERE run_id=?", (row["run_id"],))
            raise BudgetDenied("clock regression")
        elapsed = now - row["started_at"]
        budget = db.execute("SELECT limit_value,consumed FROM budgets WHERE run_id=? AND dimension='wall_clock_seconds'", (row["run_id"],)).fetchone()
        consumed = max(budget[1], elapsed)
        db.execute("UPDATE budgets SET consumed=? WHERE run_id=? AND dimension='wall_clock_seconds'", (consumed,row["run_id"]))
        db.execute("UPDATE runs SET last_clock=?,last_activity_at=? WHERE run_id=?", (now,now,row["run_id"]))
        if consumed > budget[0]:
            db.execute("UPDATE runs SET state='EXHAUSTED' WHERE run_id=?", (row["run_id"],))
            raise BudgetDenied("wall clock exhausted")

    def _consume(self, db, run_id, amounts, now):
        for dimension, amount in amounts.items():
            if dimension not in DIMENSIONS: raise BudgetError("unknown dimension")
            amount = integer(amount, "amount")
            budget = db.execute("SELECT limit_value,consumed FROM budgets WHERE run_id=? AND dimension=?", (run_id,dimension)).fetchone()
            if not budget: raise BudgetDenied("missing budget")
            if amount > budget[0] - budget[1]:
                db.execute("UPDATE runs SET state='EXHAUSTED' WHERE run_id=?", (run_id,))
                self.event(db, run_id, "BUDGET_EXHAUSTED", {"dimension":dimension}, now)
                raise BudgetDenied(f"{dimension} exhausted")
            db.execute("UPDATE budgets SET consumed=consumed+? WHERE run_id=? AND dimension=?", (amount,run_id,dimension))

    def reserve(self, run_id, amounts):
        now = self.now()
        try:
            with self.transaction() as db:
                if db.execute("SELECT frozen FROM control WHERE singleton=1").fetchone()[0]: raise BudgetDenied("system frozen")
                chain = self.ancestry(db, run_id)
                for row in chain:
                    if row["state"] != "RUNNING": raise BudgetDenied("run unavailable")
                    self._clock(db, row, now)
                for row in chain: self._consume(db, row["run_id"], amounts, now)
                self.event(db, run_id, "RESERVED", amounts, now)
        except BudgetDenied as error:
            if "exhausted" in str(error) or "clock regression" in str(error):
                with self.transaction() as db:
                    db.execute("UPDATE runs SET state='EXHAUSTED' WHERE run_id=? AND state='RUNNING'", (run_id,))
                    self.event(db, run_id, "FAIL_CLOSED_EXHAUSTED", {"reason":str(error)}, now)
            raise

    def record_result(self, run_id, success, duration_ms=0):
        integer(duration_ms, "duration")
        with self.transaction() as db: self.event(db, run_id, "RESULT", {"success":bool(success),"duration_ms":duration_ms}, self.now())

    def set_state(self, run_id, state, owner_authorized=False, provenance=""):
        if state not in STATES: raise BudgetError("invalid state")
        with self.transaction() as db:
            row = db.execute("SELECT state FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row: raise BudgetDenied("unknown run")
            old = row[0]
            if old in TERMINAL: raise BudgetDenied("terminal run")
            if state == "RUNNING" and old in {"EXHAUSTED","PAUSED","FROZEN"} and not owner_authorized: raise BudgetDenied("owner required")
            db.execute("UPDATE runs SET state=? WHERE run_id=?", (state,run_id))
            self.event(db, run_id, "STATE", {"from":old,"to":state,"owner":bool(owner_authorized),"provenance":provenance}, self.now())

    def set_frozen(self, frozen, owner_authorized=False, provenance=""):
        if not owner_authorized: raise BudgetDenied("owner required")
        with self.transaction() as db:
            now = self.now(); db.execute("UPDATE control SET frozen=?,updated_at=? WHERE singleton=1", (int(bool(frozen)),now))
            self.event(db, None, "GLOBAL_FREEZE", {"frozen":bool(frozen),"provenance":provenance}, now)

    def change_limit(self, run_id, dimension, new_limit, actor="agent", owner_authorized=False, provenance=""):
        if dimension not in DIMENSIONS: raise BudgetError("unknown dimension")
        new_limit = integer(new_limit, "limit")
        with self.transaction() as db:
            old = db.execute("SELECT limit_value,consumed FROM budgets WHERE run_id=? AND dimension=?", (run_id,dimension)).fetchone()
            if not old: raise BudgetDenied("unknown run")
            if new_limit > old[0] and (not owner_authorized or actor != "owner" or not provenance): raise BudgetDenied("fresh Owner authorization required")
            if new_limit < old[1]: raise BudgetDenied("limit below consumed")
            db.execute("UPDATE budgets SET limit_value=? WHERE run_id=? AND dimension=?", (new_limit,run_id,dimension))
            digest = self.event(db, run_id, "LIMIT_CHANGED", {"dimension":dimension,"old":old[0],"new":new_limit,"actor":actor,"provenance":provenance}, self.now())
            if new_limit > old[0]: db.execute("INSERT INTO overrides(run_id,dimension,old_limit,new_limit,provenance,event_hash) VALUES(?,?,?,?,?,?)", (run_id,dimension,old[0],new_limit,provenance,digest))

    def status(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row: raise BudgetDenied("unknown run")
            budgets = {r["dimension"]:{"limit":r["limit_value"],"consumed":r["consumed"]} for r in db.execute("SELECT * FROM budgets WHERE run_id=?", (run_id,))}
            return {**dict(row),"budgets":budgets,"frozen":bool(db.execute("SELECT frozen FROM control WHERE singleton=1").fetchone()[0])}

    def verify_ledger(self):
        previous = "0" * 64
        with self.connect() as db:
            for row in db.execute("SELECT * FROM events ORDER BY seq"):
                payload = json.loads(row["payload_json"])
                body = json.dumps({"run_id":row["run_id"],"event_type":row["event_type"],"payload":payload,"created_at":row["created_at"]}, sort_keys=True, separators=(",",":"))
                if row["previous_hash"] != previous or hashlib.sha256((previous+body).encode()).hexdigest() != row["event_hash"]: return False
                previous = row["event_hash"]
        return True
