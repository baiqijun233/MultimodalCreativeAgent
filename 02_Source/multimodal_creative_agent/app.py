"""FastAPI application entry point for local or Redis/Celery deployments."""

from __future__ import annotations

import os

from runtime import build_runtime_agent
from short_drama_agent import create_fastapi_app


agent = build_runtime_agent()
if os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL"):
    from celery_worker import CeleryTaskRunner

    runner = CeleryTaskRunner(agent)
else:
    from async_runner import AsyncTaskRunner

    runner = AsyncTaskRunner(agent)

app = create_fastapi_app(agent, runner)
