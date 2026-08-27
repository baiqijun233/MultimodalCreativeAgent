"""Build a configured Agent from environment variables without exposing secrets."""

from __future__ import annotations

import os
from pathlib import Path

from common.assets import LocalAssetStore
from common.events import InMemoryEventBus
from common.storage import TaskStore
from short_drama_agent import ShortDramaAgent


def build_runtime_agent() -> ShortDramaAgent:
    database_path = Path(os.getenv("TASK_DATABASE_PATH", ".runtime/tasks.db")).expanduser()
    asset_root = Path(os.getenv("ASSET_ROOT", ".runtime/assets")).expanduser()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    asset_root.mkdir(parents=True, exist_ok=True)
    store = TaskStore(database_path)
    event_bus = InMemoryEventBus()
    if os.getenv("REDIS_URL"):
        from integrations.redis_backend import RedisEventBus, RedisStateCache

        event_bus = RedisEventBus()
        state_cache = RedisStateCache()
    else:
        state_cache = None
    return ShortDramaAgent(store=store, asset_store=LocalAssetStore(asset_root), event_bus=event_bus, state_cache=state_cache)
