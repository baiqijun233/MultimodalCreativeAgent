"""Deterministic multi-step multimodal task agent.

The model adapter is intentionally injectable. Production code can replace it
with a VLM/LLM client without changing orchestration or persistence logic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from common.storage import TaskRecord, TaskStore, utc_now
from common.assets import LocalAssetStore
from common.events import InMemoryEventBus


class ModelAdapter(Protocol):
    def generate(self, stage: str, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class DeterministicModel:
    """Offline adapter for demos and tests."""

    def generate(self, stage: str, payload: dict[str, Any]) -> dict[str, Any]:
        if stage == "analyze":
            return {
                "intent": payload["request"].strip(),
                "content_type": "short_drama",
                "constraints": payload.get("constraints", []),
            }
        if stage == "plan":
            return {
                "characters": [{"name": "主角", "role": "推动剧情"}],
                "scenes": ["开场", "发展", "收束"],
                "storyboard": [
                    {"scene": "开场", "shot": "建立镜头"},
                    {"scene": "发展", "shot": "动作镜头"},
                    {"scene": "收束", "shot": "情绪落点"},
                ],
                "asset_types": ["image", "video", "audio"],
            }
        if stage == "validate":
            characters = payload.get("characters", [])
            scenes = payload.get("scenes", [])
            storyboard = payload.get("storyboard", [])
            asset_types = payload.get("asset_types", [])
            checks = {
                "has_characters": bool(characters),
                "has_scenes": bool(scenes),
                "storyboard_matches_scenes": len(storyboard) == len(scenes),
                "has_supported_asset_types": all(name in {"image", "video", "audio"} for name in asset_types),
            }
            return {"passed": all(checks.values()), "checks": checks, "asset_types": asset_types}
        if stage == "assets":
            return {
                "asset_jobs": [
                    {"job_id": f"asset-{index}", "type": name, "status": "queued"}
                    for index, name in enumerate(payload["asset_types"], start=1)
                ]
            }
        if stage == "finalize":
            return {"status": "ready", "manifest_version": 1, "asset_count": len(payload["asset_jobs"])}
        raise ValueError(f"不支持的模型阶段: {stage}")


class ShortDramaAgent:
    STAGES = ("analyze", "plan", "validate", "assets", "finalize")

    def __init__(self, store: TaskStore | None = None, model: ModelAdapter | None = None, max_retries: int = 2, asset_store: LocalAssetStore | None = None, event_bus: InMemoryEventBus | None = None) -> None:
        self.store = store or TaskStore()
        self.model = model or DeterministicModel()
        self.max_retries = max(0, int(max_retries))
        self.asset_store = asset_store
        self.event_bus = event_bus or InMemoryEventBus()

    def create_task(self, request: str, constraints: list[str] | None = None) -> TaskRecord:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request 必须是非空字符串")
        clean_constraints = [] if constraints is None else constraints
        if not isinstance(clean_constraints, list) or any(not isinstance(x, str) for x in clean_constraints):
            raise ValueError("constraints 必须是字符串列表")
        task_id = uuid.uuid4().hex
        record = TaskRecord(
            task_id,
            "short_drama_agent",
            "queued",
            {
                "request": request.strip(),
                "constraints": clean_constraints,
                "stage_results": {},
                "attempts": {},
                "retry_log": [],
                "errors": [],
                "events": [],
            },
            utc_now(),
        )
        self.store.save(record)
        return record

    def run(self, task_id: str) -> TaskRecord:
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id 必须是非空字符串")
        record = self.store.get(task_id)
        if record is None:
            raise KeyError(f"任务不存在: {task_id}")
        if record.status == "succeeded":
            return record
        state = dict(record.state)
        stage_results = dict(state.get("stage_results", {}))
        for stage in self.STAGES:
            if stage in stage_results:
                continue
            state["current_stage"] = stage
            self._record_event(record.task_id, state, "stage_started", {"stage": stage})
            self._save(record, "running", state)
            try:
                payload = self._payload_for(stage, state, stage_results)
                result = self._run_with_retry(stage, payload, state)
                if stage == "validate" and result.get("passed") is not True:
                    raise RuntimeError(f"一致性校验未通过: {result.get('checks', {})}")
                if stage == "assets" and self.asset_store is not None:
                    result = {**result, "asset_jobs": self.asset_store.archive_jobs(record.task_id, result.get("asset_jobs", []))}
            except RuntimeError as exc:
                state["errors"] = [
                    *state.get("errors", []),
                    {"stage": stage, "message": str(exc), "at": utc_now()},
                ]
                self._save(record, "failed", state)
                self._record_event(record.task_id, state, "task_failed", {"stage": stage, "message": str(exc)})
                self._save(record, "failed", state)
                raise
            except Exception as exc:
                wrapped = RuntimeError(f"阶段 {stage} 执行失败: {exc}")
                state["errors"] = [
                    *state.get("errors", []),
                    {"stage": stage, "message": str(wrapped), "at": utc_now()},
                ]
                self._record_event(record.task_id, state, "task_failed", {"stage": stage, "message": str(wrapped)})
                self._save(record, "failed", state)
                raise wrapped from exc
            stage_results[stage] = result
            state["stage_results"] = stage_results
            self._record_event(record.task_id, state, "stage_succeeded", {"stage": stage})
            self._save(record, "running", state)
        state["current_stage"] = None
        state["result"] = stage_results["finalize"]
        self._record_event(record.task_id, state, "task_succeeded", {"asset_count": state["result"].get("asset_count", 0)})
        return self._save(record, "succeeded", state)

    def _run_with_retry(self, stage: str, payload: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []
        for attempt in range(self.max_retries + 1):
            try:
                result = self.model.generate(stage, payload)
                if not isinstance(result, dict):
                    raise TypeError("模型结果必须是对象")
                state["attempts"] = {**state.get("attempts", {}), stage: attempt + 1}
                return result
            except Exception as exc:  # adapter failures are persisted for recovery
                message = str(exc) or exc.__class__.__name__
                errors.append(message)
                state["retry_log"] = [
                    *state.get("retry_log", []),
                    {"stage": stage, "attempt": attempt + 1, "message": message, "at": utc_now()},
                ]
        state["attempts"] = {**state.get("attempts", {}), stage: len(errors)}
        raise RuntimeError(f"阶段 {stage} 重试耗尽: {'; '.join(errors)}")

    @staticmethod
    def _payload_for(stage: str, state: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
        if stage == "analyze":
            return {"request": state["request"], "constraints": state["constraints"]}
        if stage == "plan":
            return results["analyze"]
        if stage == "validate":
            return results["plan"]
        if stage == "assets":
            return {"asset_types": results["validate"]["asset_types"]}
        return results["assets"]

    def _save(self, original: TaskRecord, status: str, state: dict[str, Any]) -> TaskRecord:
        updated = TaskRecord(original.task_id, original.task_type, status, state, utc_now())
        self.store.save(updated)
        return updated

    def _record_event(self, task_id: str, state: dict[str, Any], event_type: str, payload: dict[str, Any]) -> None:
        event = self.event_bus.publish(task_id, event_type, payload)
        state["events"] = [*state.get("events", []), event]


def create_fastapi_app(agent: ShortDramaAgent, runner: Any | None = None):
    """Optional FastAPI adapter; imported only when the dependency is present."""
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
    except ImportError as exc:
        raise RuntimeError("安装 fastapi 和 pydantic 后才能启用 HTTP 接口") from exc

    class CreateRequest(BaseModel):
        request: str
        constraints: list[str] = []

    app = FastAPI(title="Multimodal Agent Demo")

    @app.post("/tasks")
    def create_task(body: CreateRequest):
        try:
            return agent.create_task(body.request, body.constraints).__dict__
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/tasks/{task_id}/run")
    def run_task(task_id: str):
        try:
            return agent.run(task_id).__dict__
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str):
        record = agent.store.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return record.__dict__

    @app.get("/tasks/{task_id}/events")
    def list_events(task_id: str):
        if agent.store.get(task_id) is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"task_id": task_id, "events": agent.event_bus.list_events(task_id)}

    @app.post("/tasks/async")
    def create_async_task(body: CreateRequest):
        if runner is None:
            raise HTTPException(status_code=503, detail="未配置异步任务执行器")
        try:
            return runner.submit(body.request, body.constraints).__dict__
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app
