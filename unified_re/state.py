"""SQLite task journals and process-cooperative resource leases."""
import json
import sqlite3
import uuid

from .common import GateError, VAR, now


class Store:
    def __init__(self, path=None):
        VAR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path or VAR / "tasks.sqlite"), timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, task_id TEXT, time TEXT, kind TEXT, data TEXT);
        CREATE TABLE IF NOT EXISTS leases(resource TEXT PRIMARY KEY, task_id TEXT, owner TEXT);
        """)
        self.owner = uuid.uuid4().hex

    def create(self, data):
        data.update({"id": uuid.uuid4().hex, "created_at": now(), "revision": 1, "generation": 1, "owner": self.owner, "completed_steps": [], "evidence": [], "stage_index": 0})
        self.save(data)
        self.event(data["id"], "created", {"target": data.get("target"), "revision": 1})
        return data

    def save(self, task):
        task["updated_at"] = now()
        self.db.execute("INSERT OR REPLACE INTO tasks VALUES(?,?)", (task["id"], json.dumps(task, ensure_ascii=False)))
        self.db.commit()

    def get(self, task_id):
        row = self.db.execute("SELECT data FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise GateError("not_found", "Unknown task")
        return json.loads(row[0])

    def event(self, task_id, kind, data):
        self.db.execute("INSERT INTO events(task_id,time,kind,data) VALUES(?,?,?,?)", (task_id, now(), kind, json.dumps(data, ensure_ascii=False)))
        self.db.commit()

    def events(self, task_id):
        return [{"id": r["id"], "time": r["time"], "kind": r["kind"], "data": json.loads(r["data"])} for r in self.db.execute("SELECT * FROM events WHERE task_id=? ORDER BY id", (task_id,))]

    def acquire(self, task_id, resources):
        # All aliases for a backend instance must declare the same canonical
        # resource key. Unknown identity never earns an interchangeable claim.
        try:
            self.db.execute("BEGIN IMMEDIATE")
            for key in sorted(set(resources)):
                row = self.db.execute("SELECT * FROM leases WHERE resource=?", (key,)).fetchone()
                if row and (row["task_id"] != task_id or row["owner"] != self.owner):
                    raise GateError("resource_busy", "Backend instance already owned", resource=key, owner_task=row["task_id"])
                self.db.execute("INSERT OR REPLACE INTO leases VALUES(?,?,?)", (key, task_id, self.owner))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def release(self, task_id):
        self.db.execute("DELETE FROM leases WHERE task_id=? AND owner=?", (task_id, self.owner))
        self.db.commit()

    def leases(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM leases")]
