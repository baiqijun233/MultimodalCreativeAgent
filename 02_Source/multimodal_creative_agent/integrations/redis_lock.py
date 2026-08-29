"""基于 Redis SET NX EX 的跨进程锁，安全释放自己的令牌。"""

from __future__ import annotations

import secrets
import time
from typing import Any


class RedisDistributedLock:
    def __init__(self, client: Any, name: str, ttl_seconds: int = 120) -> None:
        if client is None or not hasattr(client, "set"):
            raise ValueError("client 必须是 Redis 客户端")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("锁名称不能为空")
        if not isinstance(ttl_seconds, int) or ttl_seconds < 1:
            raise ValueError("ttl_seconds 必须是正整数")
        self.client = client
        self.name = name.strip()
        self.ttl_seconds = ttl_seconds
        self.token = secrets.token_urlsafe(24)
        self.acquired = False

    def acquire(self, blocking_timeout: float = 5.0, retry_interval: float = 0.1) -> bool:
        deadline = time.monotonic() + max(0.0, float(blocking_timeout))
        while True:
            if self.client.set(self.name, self.token, nx=True, ex=self.ttl_seconds):
                self.acquired = True
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(max(0.01, float(retry_interval)))

    def release(self) -> bool:
        if not self.acquired:
            return False
        script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
        result = self.client.eval(script, 1, self.name, self.token)
        self.acquired = False
        return bool(result)

    def __enter__(self):
        if not self.acquire():
            raise TimeoutError(f"获取分布式锁超时: {self.name}")
        return self

    def __exit__(self, *_exc):
        self.release()
