from __future__ import annotations

import json
import sqlite3
from pathlib import Path

HERMES_HOME = Path(r"C:\Users\m7mdk\AppData\Local\hermes")
DARWIN_REPO = Path(r"C:\Users\m7mdk\DARWIN\darwin-zero0")
BOARD_SLUG = "darwin-zero0"

def _safe_json(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}

def _ro_connect(path):
    uri = "file:" + path.resolve().as_posix() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=2)
    db.row_factory = sqlite3.Row
    return db

def _db_health(path):
    if not path.exists():
        return "MISSING"
    try:
        with _ro_connect(path) as db:
            result = db.execute("PRAGMA quick_check").fetchone()
        return "OK" if result and result[0] == "ok" else "DEGRADED"
    except Exception:
        return "DEGRADED"

def _git_head(repo):
    git = repo / ".git"
    if git.is_file():
        try:
            text = git.read_text(encoding="utf-8").strip()
            if text.lower().startswith("gitdir:"):
                git = (repo / text.split(":", 1)[1].strip()).resolve()
        except Exception:
            return "UNKNOWN"
    try:
        value = (git / "HEAD").read_text(encoding="utf-8").strip()
    except Exception:
        return "UNKNOWN"
    if not value.startswith("ref:"):
        return value[:40]
    ref = value.split(":", 1)[1].strip()
    try:
        return (git / ref).read_text(encoding="utf-8").strip()[:40]
    except Exception:
        try:
            for line in (git / "packed-refs").read_text(encoding="utf-8").splitlines():
                if line and not line.startswith("#") and " " in line:
                    sha, name = line.split(" ", 1)
                    if name.strip() == ref:
                        return sha[:40]
        except Exception:
            pass
    return "UNKNOWN"

def _plugin_version(name):
    path = HERMES_HOME / "plugins" / name / "plugin.yaml"
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version:"):
                return line.split(":", 1)[1].strip().strip("'\"")
    except Exception:
        pass
    return "UNKNOWN"

def _kanban_summary(db_path):
    empty = {
        "name": "No active task",
        "progress": "0%",
        "progress_percent": 0,
        "status": "EMPTY",
        "task_status": "none",
        "task_id": "",
        "assignee": "",
        "counts": {"total": 0, "done": 0, "running": 0, "blocked": 0, "review": 0},
    }
    if not db_path.exists():
        return {**empty, "status": "UNKNOWN"}

    try:
        with _ro_connect(db_path) as db:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(tasks)")}
            required = {"id", "title", "status", "assignee", "priority", "created_at", "started_at", "completed_at"}
            if not required.issubset(columns):
                return {**empty, "status": "DEGRADED"}

            rows = db.execute(
                "SELECT status, COUNT(*) AS n FROM tasks WHERE status != 'archived' GROUP BY status"
            ).fetchall()
            counts = {str(row["status"]): int(row["n"]) for row in rows}
            total = sum(counts.values())
            done = counts.get("done", 0)
            percent = 100 if total and done == total else (round(done * 100 / total) if total else 0)

            current = db.execute(
                """
                SELECT id, title, assignee, status, priority, created_at, started_at, completed_at
                FROM tasks
                WHERE status != 'archived'
                ORDER BY
                  CASE status
                    WHEN 'running' THEN 0
                    WHEN 'review' THEN 1
                    WHEN 'blocked' THEN 2
                    WHEN 'ready' THEN 3
                    WHEN 'todo' THEN 4
                    WHEN 'scheduled' THEN 5
                    WHEN 'triage' THEN 6
                    WHEN 'done' THEN 7
                    ELSE 8
                  END,
                  COALESCE(started_at, completed_at, created_at) DESC,
                  priority DESC,
                  created_at DESC
                LIMIT 1
                """
            ).fetchone()

        if not current:
            return empty

        return {
            "name": str(current["title"] or "Untitled task")[:180],
            "progress": f"{percent}%",
            "progress_percent": percent,
            "status": "OK",
            "task_status": str(current["status"] or "unknown")[:32],
            "task_id": str(current["id"] or "")[:128],
            "assignee": str(current["assignee"] or "unassigned")[:96],
            "counts": {
                "total": total,
                "done": done,
                "running": counts.get("running", 0),
                "blocked": counts.get("blocked", 0),
                "review": counts.get("review", 0),
            },
        }
    except Exception:
        return {**empty, "status": "DEGRADED"}

class RuntimeSources:
    def __init__(self):
        self.telemetry = HERMES_HOME / "darwin" / "telemetry" / "events.sqlite3"
        self.supervisor = HERMES_HOME / "darwin" / "supervisor" / "decisions.sqlite3"
        self.budget = HERMES_HOME / "darwin" / "run-control" / "budget.sqlite3"
        self.context = HERMES_HOME / "darwin" / "context" / "context.sqlite3"
        self.usage = HERMES_HOME / "darwin" / "model-control" / "usage.sqlite3"
        self.skills = HERMES_HOME / "darwin" / "model-control" / "skill-registry.sqlite3"
        self.board = HERMES_HOME / "kanban" / "boards" / BOARD_SLUG / "board.json"
        self.kanban_db = HERMES_HOME / "kanban" / "boards" / BOARD_SLUG / "kanban.db"
        self.recovery_root = HERMES_HOME / "darwin" / "recovery"

    def readers(self):
        return {
            "system": self.system, "task": self.task, "control": self.control,
            "budget": self.budget_state, "model": self.model,
            "recovery": self.recovery, "context": self.context_state,
            "git": self.git, "security": self.security,
        }

    def system(self):
        return {
            "state": "RUNNING" if self.telemetry.exists() else "UNKNOWN",
            "safety_version": _plugin_version("darwin-tool-policy"),
            "acceptance_version": _plugin_version("darwin-acceptance-gate"),
        }

    def task(self):
        task = _kanban_summary(self.kanban_db)
        meta = _safe_json(self.board)
        task["board"] = str(meta.get("name") or BOARD_SLUG)[:96]
        task["source"] = "KANBAN_SQLITE"
        return task

    def control(self):
        return {
            "state": "AVAILABLE" if self.budget.exists() else "UNKNOWN",
            "approvals_mode": "manual",
            "supervisor": _db_health(self.supervisor),
        }

    def budget_state(self):
        return {"status": _db_health(self.budget), "spend": "$0 default", "source": "CP11"}

    def model(self):
        return {
            "model": "CONTROLLED",
            "router": "REPO_SIDE_DETERMINISTIC",
            "usage_ledger": _db_health(self.usage),
            "skill_registry": _db_health(self.skills),
            "cost_boundary": "LIMITED_TO_CONTROLLED_BOUNDARY",
        }

    def recovery(self):
        latest = "NONE"
        try:
            candidates = [p for p in self.recovery_root.iterdir() if p.is_dir()]
            if candidates:
                latest = max(candidates, key=lambda p: p.stat().st_mtime).name[:180]
        except Exception:
            pass
        return {"status": "OK" if self.recovery_root.exists() else "UNKNOWN", "latest": latest}

    def context_state(self):
        return {"status": _db_health(self.context), "mode": "DETERMINISTIC_LOCAL"}

    def git(self):
        return {"commit": _git_head(DARWIN_REPO), "ci": "SEE_GITHUB"}

    def security(self):
        return {
            "last_alert": "NONE",
            "telemetry": _db_health(self.telemetry),
            "source_of_truth": "CONTROL_PLANE",
        }
