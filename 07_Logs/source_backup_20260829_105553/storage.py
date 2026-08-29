"""Small SQLite task store used by both demos."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskRecord:
    task_id: str
    task_type: str
    status: str
    state: dict[str, Any]
    updated_at: str


class TaskStore:
    """Thread-safe persistence with explicit status transitions."""

    def __init__(self, database_path: str | Path = ":memory:") -> None:
        self.database_path = str(database_path)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def save(self, record: TaskRecord) -> None:
        if not record.task_id or not record.task_type or not record.status:
            raise ValueError("task_id、task_type 和 status 不能为空")
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO tasks(task_id, task_type, status, state_json, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    task_type=excluded.task_type,
                    status=excluded.status,
                    state_json=excluded.state_json,
                    updated_at=excluded.updated_at
                """,
                (record.task_id, record.task_type, record.status, json.dumps(record.state, ensure_ascii=False), record.updated_at),
            )
            self._connection.commit()

    def get(self, task_id: str) -> TaskRecord | None:
        if not task_id:
            return None
        with self._lock:
            row = self._connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return TaskRecord(row["task_id"], row["task_type"], row["status"], json.loads(row["state_json"]), row["updated_at"])

    def list_records(self, limit: int = 100) -> list[TaskRecord]:
        """按最近更新时间返回任务，供控制台和清理任务使用。"""
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit 必须是 1 到 1000 的整数")
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [TaskRecord(row["task_id"], row["task_type"], row["status"], json.loads(row["state_json"]), row["updated_at"]) for row in rows]

    def delete(self, task_id: str) -> bool:
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id 必须是非空字符串")
        with self._lock:
            cursor = self._connection.execute("DELETE FROM tasks WHERE task_id = ?", (task_id.strip(),))
            self._connection.commit()
        return cursor.rowcount > 0

    def ping(self) -> bool:
        """执行最小数据库读操作，供就绪检查使用。"""
        with self._lock:
            self._connection.execute("SELECT 1").fetchone()
        return True

    def close(self) -> None:
        with self._lock:
            self._connection.close()


def record_to_dict(record: TaskRecord) -> dict[str, Any]:
    return asdict(record)
