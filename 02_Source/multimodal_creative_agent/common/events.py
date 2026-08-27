"""Small in-memory event sink for progress polling and SSE/WebSocket adapters."""

from __future__ import annotations

import threading
import uuid
from typing import Any


class InMemoryEventBus:
    def __init__(self) -> None:
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.RLock()

    def publish(self, task_id: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id 必须是非空字符串")
        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("event_type 必须是非空字符串")
        event = {
            "event_id": uuid.uuid4().hex,
            "task_id": task_id,
            "type": event_type,
            "payload": payload or {},
        }
        with self._lock:
            self._events.setdefault(task_id, []).append(event)
        return event

    def list_events(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(event) for event in self._events.get(task_id, [])]
