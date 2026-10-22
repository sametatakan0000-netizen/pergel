"""Kalıcı SQLite WAL İş Kuyruğu (Job Store)."""
from contextlib import closing
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


class JobStore:
    """Tarayıcı ve kazıma görevlerini SQLite WAL modunda kalıcı olarak yönetir."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS browse_jobs (
                    job_id TEXT PRIMARY KEY,
                    session_name TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    needs_vision INTEGER NOT NULL,
                    js_complexity TEXT NOT NULL,
                    webhook_url TEXT,
                    status TEXT NOT NULL,
                    engine TEXT,
                    extracted_markdown TEXT,
                    oracle_passed INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    def create_job(
        self,
        target_url: str,
        goal: str = "",
        needs_vision: bool = False,
        js_complexity: str = "low",
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        job_id = f"job_{uuid.uuid4().hex[:10]}"
        session_name = f"farm_{job_id}"
        now = time.time()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO browse_jobs (
                    job_id, session_name, target_url, goal, needs_vision,
                    js_complexity, webhook_url, status, engine, extracted_markdown,
                    oracle_passed, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', '', '', 0, ?, ?)
                """,
                (
                    job_id,
                    session_name,
                    target_url,
                    goal,
                    1 if needs_vision else 0,
                    js_complexity,
                    webhook_url,
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get_job(job_id)

    def mark_running(self, job_id: str, engine: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "UPDATE browse_jobs SET status = 'running', engine = ?, updated_at = ? WHERE job_id = ?",
                (engine, time.time(), job_id),
            )
            conn.commit()

    def mark_completed(
        self,
        job_id: str,
        engine: str,
        extracted_markdown: str,
        oracle_passed: bool,
    ) -> None:
        status = "completed" if oracle_passed else "failed"
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                UPDATE browse_jobs
                SET status = ?, engine = ?, extracted_markdown = ?, oracle_passed = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    status,
                    engine,
                    extracted_markdown,
                    1 if oracle_passed else 0,
                    time.time(),
                    job_id,
                ),
            )
            conn.commit()

    def get_job(self, job_id: str) -> Dict[str, Any]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM browse_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if not row:
            raise KeyError(f"Job not found: {job_id}")
        data = dict(row)
        data["needs_vision"] = bool(data["needs_vision"])
        data["oracle_passed"] = bool(data["oracle_passed"])
        return data

    def list_jobs(self, limit: int = 20) -> List[Dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM browse_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["needs_vision"] = bool(d["needs_vision"])
            d["oracle_passed"] = bool(d["oracle_passed"])
            results.append(d)
        return results
