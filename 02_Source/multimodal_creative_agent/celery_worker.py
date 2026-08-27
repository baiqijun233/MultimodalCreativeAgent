"""Celery entry point for running the same persisted Agent task in a worker."""

from __future__ import annotations

import os
from pathlib import Path


def create_celery_app():
    try:
        from celery import Celery
    except ImportError as exc:
        raise RuntimeError("使用 Celery 前请安装 celery 包") from exc
    broker = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL")
    if not broker:
        raise RuntimeError("未设置 CELERY_BROKER_URL 或 REDIS_URL")
    backend = os.getenv("CELERY_RESULT_BACKEND", broker)
    app = Celery("multimodal_creative_agent", broker=broker, backend=backend)
    app.conf.update(task_track_started=True, task_acks_late=True, worker_prefetch_multiplier=1)

    @app.task(bind=True, name="creative.run_task", autoretry_for=(RuntimeError,), retry_backoff=True, max_retries=2)
    def run_task(_self, task_id: str) -> dict:
        from runtime import build_runtime_agent

        result = build_runtime_agent().run(task_id)
        return result.__dict__

    app.run_task = run_task
    return app


class CeleryTaskRunner:
    def __init__(self, agent) -> None:
        self.agent = agent
        self.app = create_celery_app()

    def submit(self, request: str, constraints: list[str] | None = None):
        record = self.agent.create_task(request, constraints)
        self.app.run_task.delay(record.task_id)
        return record

    def submit_existing(self, task_id: str):
        record = self.agent.store.get(task_id)
        if record is None:
            raise KeyError(f"任务不存在: {task_id}")
        self.app.run_task.delay(task_id)
        return record

    def close(self) -> None:
        return None


# Celery CLI loads this object with `-A celery_worker:app`. In local tests the
# broker may be absent, so keep import errors deferred until the app is used.
try:
    app = create_celery_app()
except RuntimeError:
    app = None
