"""Deterministic multi-step multimodal task agent.

The model adapter is intentionally injectable. Production code can replace it
with a VLM/LLM client without changing orchestration or persistence logic.
"""

import asyncio
import os
import time
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

    def __init__(self, store: TaskStore | None = None, model: ModelAdapter | None = None, max_retries: int = 2, asset_store: LocalAssetStore | None = None, event_bus: InMemoryEventBus | None = None, state_cache: Any | None = None) -> None:
        self.store = store or TaskStore()
        self.model = model or DeterministicModel()
        self.max_retries = max(0, int(max_retries))
        self.asset_store = asset_store
        self.event_bus = event_bus or InMemoryEventBus()
        self.state_cache = state_cache

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
        if self.state_cache is not None:
            self.state_cache.set(updated.task_id, {"status": updated.status, **updated.state})
        return updated

    def _record_event(self, task_id: str, state: dict[str, Any], event_type: str, payload: dict[str, Any]) -> None:
        event = self.event_bus.publish(task_id, event_type, payload)
        state["events"] = [*state.get("events", []), event]


def create_fastapi_app(agent: ShortDramaAgent, runner: Any | None = None):
    """Optional FastAPI adapter; imported only when the dependency is present."""
    try:
        from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
        from pydantic import BaseModel
        from integrations.artclaw import ArtClawClient
    except ImportError as exc:
        raise RuntimeError("安装 fastapi 和 pydantic 后才能启用 HTTP 接口") from exc

    class CreateRequest(BaseModel):
        request: str
        constraints: list[str] = []

    class ArtClawVideoRequest(BaseModel):
        prompt: str
        reference_urls: list[str] = []
        duration_seconds: int = 4
        confirm_paid: bool = False

    app = FastAPI(title="Multimodal Agent Demo")

    def get_artclaw_client() -> ArtClawClient:
        return ArtClawClient()

    @app.post("/artclaw/videos")
    def submit_artclaw_video(body: ArtClawVideoRequest):
        """由平台直接提交 ArtClaw 视频任务；生成过程通过任务编号查询。"""
        if body.confirm_paid is not True:
            raise HTTPException(status_code=400, detail="请将 confirm_paid 设为 true，确认可能产生费用")
        try:
            result = get_artclaw_client().submit_video(
                body.prompt,
                body.reference_urls,
                duration_seconds=body.duration_seconds,
                allow_paid=True,
            )
            return result
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/artclaw/videos/{job_id}")
    def get_artclaw_video(job_id: str):
        try:
            return get_artclaw_client().get_job(job_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/tasks/{task_id}/artclaw-submit")
    def submit_task_storyboard_to_artclaw(task_id: str, body: ArtClawVideoRequest):
        """把已完成的规划阶段分镜批量提交到 ArtClaw。"""
        if body.confirm_paid is not True:
            raise HTTPException(status_code=400, detail="请将 confirm_paid 设为 true，确认可能产生费用")
        record = agent.store.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        storyboard = record.state.get("stage_results", {}).get("plan", {}).get("storyboard", [])
        if not isinstance(storyboard, list) or not storyboard:
            raise HTTPException(status_code=409, detail="任务尚未完成分镜规划")
        existing = record.state.get("artclaw_jobs", [])
        existing_by_index = {item.get("shot_index"): item for item in existing if isinstance(item, dict)}
        client = get_artclaw_client()
        submitted = []
        try:
            for index, shot in enumerate(storyboard, start=1):
                if not isinstance(shot, dict):
                    raise ValueError("分镜项必须是对象")
                if index in existing_by_index:
                    submitted.append(existing_by_index[index])
                    continue
                prompt = shot.get("prompt") or shot.get("shot")
                result = client.submit_video(
                    str(prompt or "").strip(),
                    body.reference_urls,
                    duration_seconds=body.duration_seconds,
                    allow_paid=True,
                )
                submitted.append({"shot_index": index, "scene": shot.get("scene", ""), "job_id": result.get("job_id"), "status": result.get("status", "pending")})
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        state = dict(record.state)
        state["artclaw_jobs"] = submitted
        agent._record_event(task_id, state, "artclaw_jobs_submitted", {"count": len(submitted)})
        saved = agent._save(record, record.status, state)
        return {"task_id": task_id, "jobs": saved.state["artclaw_jobs"]}

    @app.get("/tasks/{task_id}/artclaw-status")
    def get_task_artclaw_status(task_id: str):
        record = agent.store.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        jobs = record.state.get("artclaw_jobs", [])
        if not isinstance(jobs, list) or not jobs:
            raise HTTPException(status_code=409, detail="任务还没有提交 ArtClaw 分镜")
        client = get_artclaw_client()
        statuses = []
        for item in jobs:
            if not isinstance(item, dict) or not item.get("job_id"):
                continue
            try:
                remote = client.get_job(str(item["job_id"]))
                statuses.append({**item, "status": remote.get("status", item.get("status")), "result": remote.get("result")})
            except RuntimeError as exc:
                statuses.append({**item, "status": "query_failed", "error": str(exc)})
        return {"task_id": task_id, "jobs": statuses}

    @app.post("/tasks/{task_id}/artclaw-download")
    def download_task_artclaw_videos(task_id: str):
        record = agent.store.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        jobs = record.state.get("artclaw_jobs", [])
        if not isinstance(jobs, list) or not jobs:
            raise HTTPException(status_code=409, detail="任务还没有提交 ArtClaw 分镜")
        client = get_artclaw_client()
        asset_root = agent.asset_store.root if agent.asset_store is not None else ".runtime/assets"
        downloaded = []
        pending = []
        for item in jobs:
            if not isinstance(item, dict) or not item.get("job_id"):
                continue
            try:
                remote = client.get_job(str(item["job_id"]))
                if remote.get("status") not in {"success", "succeeded", "completed"}:
                    pending.append({"shot_index": item.get("shot_index"), "job_id": item.get("job_id"), "status": remote.get("status")})
                    continue
                path = client.download_result(remote, asset_root)
                downloaded.append({"shot_index": item.get("shot_index"), "job_id": item.get("job_id"), "local_file": str(path)})
            except (ValueError, RuntimeError) as exc:
                pending.append({"shot_index": item.get("shot_index"), "job_id": item.get("job_id"), "status": "download_failed", "error": str(exc)})
        return {"task_id": task_id, "downloaded": downloaded, "pending": pending}

    @app.post("/artclaw/videos/{job_id}/download")
    def download_artclaw_video(job_id: str):
        try:
            client = get_artclaw_client()
            job = client.get_job(job_id)
            if job.get("status") not in {"success", "succeeded", "completed"}:
                raise HTTPException(status_code=409, detail="视频尚未生成完成，请稍后重试")
            asset_root = agent.asset_store.root if agent.asset_store is not None else ".runtime/assets"
            path = client.download_result(job, asset_root)
            return {"job_id": job_id, "status": "downloaded", "local_file": str(path)}
        except HTTPException:
            raise
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "multimodal-creative-agent"}

    @app.websocket("/ws/tasks/{task_id}")
    async def task_websocket(websocket: WebSocket, task_id: str):
        await websocket.accept()
        if agent.store.get(task_id) is None:
            await websocket.close(code=4404, reason="任务不存在")
            return
        sent = 0
        timeout_seconds = max(5.0, float(os.getenv("WEBSOCKET_TASK_TIMEOUT_SECONDS", "120")))
        deadline = time.monotonic() + timeout_seconds
        try:
            while time.monotonic() < deadline:
                events = agent.event_bus.list_events(task_id)
                for event in events[sent:]:
                    await websocket.send_json(event)
                sent = len(events)
                record = agent.store.get(task_id)
                if record is not None and record.status in {"succeeded", "failed"}:
                    await websocket.send_json({"type": "task_snapshot", "payload": record.__dict__})
                    return
                await asyncio.sleep(0.25)
            await websocket.send_json({"type": "timeout", "payload": {"task_id": task_id}})
        except WebSocketDisconnect:
            return

    return app
