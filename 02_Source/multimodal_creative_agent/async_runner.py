"""Thread-pool execution boundary for local asynchronous task demos."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from common.storage import TaskRecord
from short_drama_agent import ShortDramaAgent


class AsyncTaskRunner:
    def __init__(self, agent: ShortDramaAgent, max_workers: int = 2) -> None:
        if not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("max_workers 必须是正整数")
        self.agent = agent
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="creative-agent")
        self._futures: dict[str, Future[TaskRecord]] = {}

    def submit(self, request: str, constraints: list[str] | None = None) -> TaskRecord:
        record = self.agent.create_task(request, constraints)
        self._futures[record.task_id] = self._executor.submit(self.agent.run, record.task_id)
        return record

    def submit_existing(self, task_id: str) -> TaskRecord:
        record = self.agent.store.get(task_id)
        if record is None:
            raise KeyError(f"任务不存在: {task_id}")
        self._futures[task_id] = self._executor.submit(self.agent.run, task_id)
        return record

    def result(self, task_id: str, timeout: float | None = None) -> TaskRecord:
        future = self._futures.get(task_id)
        if future is None:
            record = self.agent.store.get(task_id)
            if record is None:
                raise KeyError(f"任务不存在: {task_id}")
            return record
        return future.result(timeout=timeout)

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)
