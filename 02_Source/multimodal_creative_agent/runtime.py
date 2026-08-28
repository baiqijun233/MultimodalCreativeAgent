"""Build a configured Agent from environment variables without exposing secrets."""

from __future__ import annotations

import os
from pathlib import Path

from common.assets import LocalAssetStore
from common.events import InMemoryEventBus
from common.storage import TaskStore
from short_drama_agent import ShortDramaAgent


def build_runtime_agent() -> ShortDramaAgent:
    project_root = Path(__file__).resolve().parents[2]
    default_runtime_root = project_root / "04_Data" / "runtime"
    database_path = Path(os.getenv("TASK_DATABASE_PATH", str(default_runtime_root / "tasks.db"))).expanduser()
    asset_root = Path(os.getenv("ASSET_ROOT", str(default_runtime_root / "assets"))).expanduser()
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
    model = None
    model_provider = os.getenv("MODEL_PROVIDER", "deepseek").strip().lower()
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if model_provider not in {"deepseek", "offline"}:
        raise ValueError("MODEL_PROVIDER 必须是 deepseek 或 offline")
    if model_provider == "deepseek" and deepseek_key:
        from integrations.deepseek import DeepSeekModel

        model = DeepSeekModel()
    agent = ShortDramaAgent(store=store, model=model, asset_store=LocalAssetStore(asset_root), event_bus=event_bus, state_cache=state_cache)
    agent.model_provider = "deepseek" if model is not None else "offline"
    return agent
