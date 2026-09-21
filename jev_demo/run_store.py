"""SQLite-backed immutable run records."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone


def _now():
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    def __init__(self, path):
        self.path = str(path)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT,
                    request TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
                    progress_current INTEGER NOT NULL DEFAULT 0,
                    progress_total INTEGER NOT NULL DEFAULT 0,
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    kind TEXT NOT NULL,
                    data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(runs)")}
            if "idempotency_key" not in columns:
                connection.execute("ALTER TABLE runs ADD COLUMN idempotency_key TEXT")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS runs_idempotency_key ON runs(idempotency_key)"
            )

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def create(self, request):
        run_id = str(uuid.uuid4())
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runs (id, request, status, created_at, updated_at) "
                "VALUES (?, ?, 'running', ?, ?)",
                (run_id, json.dumps(request), timestamp, timestamp),
            )
        return run_id

    def create_once(self, request, idempotency_key):
        if not idempotency_key:
            return self.create(request), True
        run_id = str(uuid.uuid4())
        timestamp = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT id, request FROM runs WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                if json.loads(existing["request"]) != request:
                    raise ValueError("idempotency key was already used for another request")
                return existing["id"], False
            connection.execute(
                "INSERT INTO runs (id, idempotency_key, request, status, created_at, updated_at) "
                "VALUES (?, ?, ?, 'running', ?, ?)",
                (run_id, idempotency_key, json.dumps(request), timestamp, timestamp),
            )
        return run_id, True

    def fail_running(self, error):
        for run in self.list():
            if run["status"] == "running":
                self.fail(run["id"], error)

    def append(self, run_id, kind, data=None):
        if isinstance(kind, str):
            records = [{"kind": kind, "data": {} if data is None else data}]
        elif isinstance(kind, dict):
            records = [kind]
        else:
            records = kind
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_running(connection, run_id)
            for record in records:
                if not isinstance(record.get("kind"), str) or not record["kind"]:
                    raise ValueError("record kind must be a non-empty string")
                connection.execute(
                    "INSERT INTO records (run_id, kind, data, timestamp) VALUES (?, ?, ?, ?)",
                    (run_id, record["kind"], json.dumps(record.get("data", {})), _now()),
                )

    def progress(self, run_id, current, total):
        if total <= 0 or current < 0 or current > total:
            raise ValueError("progress must satisfy 0 <= current <= total and total > 0")
        timestamp = _now()
        data = {"current": current, "total": total}
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_running(connection, run_id)
            connection.execute(
                "UPDATE runs SET progress_current = ?, progress_total = ?, updated_at = ? WHERE id = ?",
                (current, total, timestamp, run_id),
            )
            connection.execute(
                "INSERT INTO records (run_id, kind, data, timestamp) VALUES (?, 'progress', ?, ?)",
                (run_id, json.dumps(data), timestamp),
            )

    def complete(self, run_id, result):
        self._finish(run_id, "completed", result=result)

    def fail(self, run_id, error):
        self._finish(run_id, "failed", error=str(error))

    def _finish(self, run_id, status, result=None, error=None):
        timestamp = _now()
        encoded_result = json.dumps(result) if result is not None else None
        data = result if status == "completed" else {"error": error}
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_running(connection, run_id)
            connection.execute(
                "UPDATE runs SET status = ?, result = ?, error = ?, updated_at = ? WHERE id = ?",
                (status, encoded_result, error, timestamp, run_id),
            )
            connection.execute(
                "INSERT INTO records (run_id, kind, data, timestamp) VALUES (?, ?, ?, ?)",
                (run_id, status, json.dumps(data), timestamp),
            )

    @staticmethod
    def _require_running(connection, run_id):
        row = connection.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        if row["status"] != "running":
            raise ValueError(f"run {run_id} is immutable")

    def list(self):
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM runs ORDER BY rowid DESC").fetchall()
        return [self._run(row) for row in rows]

    def read(self, run_id):
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            records = connection.execute(
                "SELECT kind, data, timestamp FROM records WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
        run = self._run(row)
        run["records"] = [
            {"kind": record["kind"], "data": json.loads(record["data"]), "timestamp": record["timestamp"]}
            for record in records
        ]
        return run

    @staticmethod
    def _run(row):
        return {
            "id": row["id"],
            "request": json.loads(row["request"]),
            "status": row["status"],
            "progress": {"current": row["progress_current"], "total": row["progress_total"]},
            "result": json.loads(row["result"]) if row["result"] is not None else None,
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
