"""Atomic workspace persistence and local SQLite FTS5 state index."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from via54sciforge.core.models import utc_now_iso


def atomic_write_text(target: Path, content: str) -> Path:
    """Atomically write UTF-8 text via temp file + os.replace."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp_", suffix=target.suffix, dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp_name, target)
    except Exception:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise
    return target


def atomic_write_json(target: Path, payload: Any) -> Path:
    """Atomically serialize a Pydantic model or JSON-compatible object."""
    if isinstance(payload, BaseModel):
        text = payload.model_dump_json(indent=2)
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return atomic_write_text(target, text)


class WorkspaceStore:
    """Manages per-run directories and an indexed SQLite state ledger (runs + FTS5)."""

    def __init__(self, runs_dir: Path, state_db_path: Path):
        self.runs_dir = runs_dir
        self.state_db_path = state_db_path
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.state_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.state_db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sciforge_runs (
                    run_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    workspace_dir TEXT NOT NULL,
                    status TEXT NOT NULL,
                    grade TEXT DEFAULT '',
                    improvement_pct REAL DEFAULT 0.0,
                    grounding_rate REAL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    summary_json_path TEXT DEFAULT ''
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS sciforge_fts USING fts5(
                    run_id UNINDEXED,
                    kind,
                    title,
                    body
                );
                """
            )

    @staticmethod
    def new_run_id(prefix: str = "sf") -> str:
        short = uuid.uuid4().hex[:8]
        stamp = utc_now_iso().replace(":", "").replace("-", "").replace("T", "_")[:15]
        return f"{prefix}_{stamp}_{short}"

    def prepare_run_dir(self, run_id: str) -> Path:
        run_dir = self.runs_dir / run_id
        for sub in ("literature", "research", "simulation", "evolution", "knowledge", "manuscript", "deliverables"):
            (run_dir / sub).mkdir(parents=True, exist_ok=True)
        return run_dir

    def record_run(
        self,
        run_id: str,
        topic: str,
        workspace_dir: Path,
        status: str,
        grade: str = "",
        improvement_pct: float = 0.0,
        grounding_rate: float = 0.0,
        summary_json_path: str = "",
    ) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sciforge_runs
                    (run_id, topic, workspace_dir, status, grade, improvement_pct, grounding_rate, created_at, updated_at, summary_json_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    grade=excluded.grade,
                    improvement_pct=excluded.improvement_pct,
                    grounding_rate=excluded.grounding_rate,
                    updated_at=excluded.updated_at,
                    summary_json_path=excluded.summary_json_path
                """,
                (
                    run_id,
                    topic,
                    str(workspace_dir),
                    status,
                    grade,
                    float(improvement_pct),
                    float(grounding_rate),
                    now,
                    now,
                    summary_json_path,
                ),
            )

    def index_text(self, run_id: str, kind: str, title: str, body: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sciforge_fts (run_id, kind, title, body) VALUES (?, ?, ?, ?)",
                (run_id, kind, title, body[:20000]),
            )

    def list_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sciforge_runs ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sciforge_runs WHERE run_id = ?", (run_id,)).fetchone()
            return dict(row) if row else None
