"""本机 SQLite 状态存储 — 幂等控制 + 断网恢复。"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "agent_jobs.db"

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id       TEXT PRIMARY KEY,
                operation    TEXT NOT NULL,
                parameters   TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'QUEUED',
                pool         TEXT NOT NULL DEFAULT 'file_read',
                client_uuid  TEXT,
                result       TEXT,
                error        TEXT,
                received_at  REAL NOT NULL,
                started_at   REAL,
                finished_at  REAL
            )
        """)
        _conn.commit()
    return _conn


def insert_job(job_id: str, operation: str, parameters: dict) -> bool:
    """插入任务，已存在返回 False（幂等）."""
    with _lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO jobs (job_id, operation, parameters, status, pool, received_at) "
                "VALUES (?, ?, ?, 'QUEUED', ?, ?)",
                (
                    job_id,
                    operation,
                    json.dumps(parameters, ensure_ascii=False),
                    _pool_for(operation),
                    time.time(),
                ),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def update_status(job_id: str, status: str, **extra) -> None:
    with _lock:
        conn = _get_conn()
        fields = ["status = ?"]
        values = [status]
        for col in ("result", "error", "client_uuid"):
            if col in extra:
                val = extra[col]
                fields.append(f"{col} = ?")
                values.append(json.dumps(val, ensure_ascii=False) if isinstance(val, dict) else val)
        if status == "RUNNING":
            fields.append("started_at = ?")
            values.append(time.time())
        if status in ("SUCCEEDED", "FAILED"):
            fields.append("finished_at = ?")
            values.append(time.time())
        values.append(job_id)
        conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE job_id = ?", values)
        conn.commit()


_JOB_COLS = [
    "job_id", "operation", "parameters", "status", "pool",
    "client_uuid", "result", "error", "received_at", "started_at", "finished_at",
]


def get_job(job_id: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    return dict(zip(_JOB_COLS, row))


def list_jobs(status: str | None = None, limit: int = 50) -> list[dict]:
    conn = _get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY received_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY received_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(zip(_JOB_COLS, r)) for r in rows]


def _pool_for(operation: str) -> str:
    from servers.agent.operation_registry import pool_for
    return pool_for(operation)

def transition_status(job_id: str, from_statuses: tuple[str, ...], to_status: str) -> bool:
    """原子状态转换 — 只有当前状态在 from_statuses 中才更新为 to_status。"""
    with _lock:
        conn = _get_conn()
        placeholders = ','.join(['?'] * len(from_statuses))
        cur = conn.execute(
            f"UPDATE jobs SET status = ? WHERE job_id = ? AND status IN ({placeholders})",
            [to_status, job_id] + list(from_statuses),
        )
        conn.commit()
        return cur.rowcount > 0
