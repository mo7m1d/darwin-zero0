import sqlite3

from owner_ops.local_ui import DASHBOARD_HTML
from owner_ops.runtime_sources import _kanban_summary

def make_db(path, rows):
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE tasks(
          id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT, assignee TEXT,
          status TEXT NOT NULL, priority INTEGER DEFAULT 0, created_by TEXT,
          created_at INTEGER NOT NULL, started_at INTEGER, completed_at INTEGER,
          workspace_kind TEXT DEFAULT 'scratch', workspace_path TEXT
        );
        """)
        db.executemany(
            "INSERT INTO tasks(id,title,assignee,status,priority,created_at,started_at,completed_at) VALUES(?,?,?,?,?,?,?,?)",
            rows,
        )

def test_kanban_summary_prefers_running_and_calculates_progress(tmp_path):
    db = tmp_path / "kanban.db"
    make_db(db, [
        ("a","Done task","d","done",0,1,1,5),
        ("b","Running task","darwin","running",5,2,3,None),
        ("c","Todo task",None,"todo",9,4,None,None),
        ("d","Archived",None,"archived",0,1,None,None),
    ])
    s = _kanban_summary(db)
    assert s["name"] == "Running task"
    assert s["task_status"] == "running"
    assert s["progress_percent"] == 33
    assert s["counts"] == {"total":3,"done":1,"running":1,"blocked":0,"review":0}

def test_kanban_summary_all_done_is_100(tmp_path):
    db = tmp_path / "kanban.db"
    make_db(db, [("a","Done","d","done",0,1,1,2)])
    s = _kanban_summary(db)
    assert s["progress_percent"] == 100
    assert s["name"] == "Done"

def test_kanban_summary_empty_not_unknown(tmp_path):
    db = tmp_path / "kanban.db"
    make_db(db, [])
    s = _kanban_summary(db)
    assert s["name"] == "No active task"
    assert s["status"] == "EMPTY"

def test_dashboard_is_cards_not_raw_json():
    assert 'class="grid"' in DASHBOARD_HTML
    assert 'id="taskName"' in DASHBOARD_HTML
    assert "JSON.stringify" not in DASHBOARD_HTML
    assert "setInterval(refresh,60000)" in DASHBOARD_HTML

def test_dashboard_has_no_external_assets():
    low = DASHBOARD_HTML.lower()
    assert "https://" not in low
    assert "http://" not in low
    assert "<iframe" not in low
    assert "<img" not in low

def test_dashboard_uses_textcontent_for_dynamic_values():
    assert ".textContent" in DASHBOARD_HTML
    assert ".innerHTML" not in DASHBOARD_HTML
