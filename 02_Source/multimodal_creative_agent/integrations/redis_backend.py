"""Optional Redis state cache and event bus."""

from __future__ import annotations

import json
import os
from typing import Any


def _redis_client(url: str | None = None):
    try:
        import redis
    except ImportError as exc:
        raise RuntimeError("使用 Redis 适配器前请安装 redis 包") from exc
    redis_url = url or os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("未设置 REDIS_URL")
    return redis.Redis.from_url(redis_url, decode_responses=True)


class RedisStateCache:
    def __init__(self, url: str | None = None, prefix: str = "creative:state:") -> None:
        self.client = _redis_client(url)
        self.prefix = prefix

    def set(self, task_id: str, state: dict[str, Any], ttl_seconds: int = 86400) -> None:
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id 必须是非空字符串")
        if not isinstance(state, dict):
            raise ValueError("state 必须是对象")
        if not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise ValueError("ttl_seconds 必须是正整数")
        self.client.setex(f"{self.prefix}{task_id.strip()}", ttl_seconds, json.dumps(state, ensure_ascii=False))

    def get(self, task_id: str) -> dict[str, Any] | None:
        if not isinstance(task_id, str) or not task_id.strip():
            return None
        value = self.client.get(f"{self.prefix}{task_id.strip()}")
        if value is None:
            return None
        result = json.loads(value)
        if not isinstance(result, dict):
            raise ValueError("Redis 中的任务状态不是对象")
        return result


class RedisEventBus:
    def __init__(self, url: str | None = None, prefix: str = "creative:events:", ttl_seconds: int = 86400) -> None:
        if not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise ValueError("ttl_seconds 必须是正整数")
        self.client = _redis_client(url)
        self.prefix = prefix
        self.ttl_seconds = ttl_seconds

    def publish(self, task_id: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        from common.events import InMemoryEventBus

        event = InMemoryEventBus().publish(task_id, event_type, payload)
        key = f"{self.prefix}{task_id}"
        self.client.rpush(key, json.dumps(event, ensure_ascii=False))
        self.client.expire(key, self.ttl_seconds)
        return event

    def list_events(self, task_id: str) -> list[dict[str, Any]]:
        if not isinstance(task_id, str) or not task_id.strip():
            return []
        values = self.client.lrange(f"{self.prefix}{task_id.strip()}", 0, -1)
        events = [json.loads(value) for value in values]
        if any(not isinstance(event, dict) for event in events):
            raise ValueError("Redis 中存在无效事件")
        return events
