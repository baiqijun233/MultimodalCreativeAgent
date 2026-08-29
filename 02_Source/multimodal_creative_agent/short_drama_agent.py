"""Deterministic multi-step multimodal task agent.

The model adapter is intentionally injectable. Production code can replace it
with a VLM/LLM client without changing orchestration or persistence logic.
"""

import asyncio
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
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
        from fastapi.responses import FileResponse
        from pydantic import BaseModel, Field
        from integrations.artclaw import ArtClawClient, normalize_reference_urls
        from integrations.image_provider import ImageProviderClient
    except ImportError as exc:
        raise RuntimeError("安装 fastapi 和 pydantic 后才能启用 HTTP 接口") from exc

    class CreateRequest(BaseModel):
        request: str = Field(min_length=1, max_length=10000)
        constraints: list[str] = Field(default_factory=list, max_length=50)

    class ArtClawVideoRequest(BaseModel):
        prompt: str = Field(min_length=1, max_length=5000)
        reference_urls: list[str] = Field(default_factory=list, max_length=9)
        duration_seconds: int = Field(default=4, ge=4, le=15)
        confirm_paid: bool = False

    class ArtClawBatchRequest(BaseModel):
        reference_urls: list[str] = Field(default_factory=list, max_length=9)
        shot_reference_urls: dict[int, list[str]] = Field(default_factory=dict, max_length=100)
        duration_seconds: int = Field(default=4, ge=4, le=15)
        max_new_jobs: int = Field(default=3, ge=1, le=10)
        confirm_paid: bool = False

    class ImageBatchRequest(BaseModel):
        max_new_images: int = Field(default=4, ge=1, le=10)
        confirm_paid: bool = False

    app = FastAPI(title="Multimodal Agent Demo")
    artclaw_submit_lock = threading.Lock()
    image_generate_lock = threading.Lock()

    def get_artclaw_client() -> ArtClawClient:
        return ArtClawClient()

    def get_image_provider_client() -> ImageProviderClient:
        return ImageProviderClient()

    def build_image_plan(task_id: str):
        record = agent.store.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        plan = record.state.get("stage_results", {}).get("plan", {})
        if not isinstance(plan, dict):
            raise HTTPException(status_code=409, detail="任务尚未完成角色与场景规划")
        characters = plan.get("characters", [])
        scenes = plan.get("scenes", [])
        if not isinstance(characters, list) or not isinstance(scenes, list) or (not characters and not scenes):
            raise HTTPException(status_code=409, detail="任务尚未形成可生成的角色或场景清单")

        request_text = str(record.state.get("request", "")).strip()[:5000]
        image_tasks: list[dict[str, str]] = []
        for index, character in enumerate(characters, start=1):
            if isinstance(character, dict):
                label = str(character.get("name") or f"角色{index}").strip()
                details = "，".join(
                    str(value).strip()
                    for key, value in character.items()
                    if key != "name" and value is not None and str(value).strip()
                )[:2000]
            else:
                label = str(character).strip() or f"角色{index}"
                details = ""
            prompt = (
                f"为短剧《{request_text}》制作角色设定参考图。角色：{label}。"
                f"角色信息：{details or '按剧情设定补全'}。"
                "单人全身正面站姿，面部、发型、服装和配色清晰，纯净中性背景，无文字、无水印，便于后续镜头保持角色一致。"
            )
            image_tasks.append({"asset_key": f"character-{index}", "kind": "character", "label": label, "prompt": prompt})

        for index, scene in enumerate(scenes, start=1):
            if isinstance(scene, dict):
                label = str(scene.get("name") or scene.get("scene") or f"场景{index}").strip()
                details = "，".join(
                    str(value).strip()
                    for key, value in scene.items()
                    if key not in {"name", "scene"} and value is not None and str(value).strip()
                )[:2000]
            else:
                label = str(scene).strip() or f"场景{index}"
                details = ""
            prompt = (
                f"为短剧《{request_text}》制作场景设定参考图。场景：{label}。"
                f"场景信息：{details or '按剧情设定补全'}。"
                "空镜建立画面，空间布局、光线、材质和主色调明确，不出现人物，无文字、无水印，便于后续镜头保持场景一致。"
            )
            image_tasks.append({"asset_key": f"scene-{index}", "kind": "scene", "label": label, "prompt": prompt})
        return record, image_tasks

    def add_reference_instructions(prompt: str, reference_count: int) -> str:
        if reference_count <= 0:
            return prompt
        reference_tokens = "、".join(f"@图片{index}" for index in range(1, reference_count + 1))
        return (
            f"{prompt}\n参考图映射：{reference_tokens}。"
            "请严格保持参考图中的角色脸型、发型、服装、场景布局和整体视觉风格连续，不要随意替换。"
        )

    @app.post("/tasks/{task_id}/image-preview")
    def preview_task_images(task_id: str, body: ImageBatchRequest):
        """免费预览图片任务清单，不调用外部图片服务。"""
        record, image_tasks = build_image_plan(task_id)
        existing = record.state.get("image_assets", [])
        planned_keys = {item["asset_key"] for item in image_tasks}
        existing_keys = {
            item.get("asset_key")
            for item in existing
            if isinstance(item, dict) and item.get("asset_key") in planned_keys
        } if isinstance(existing, list) else set()
        preview = [{**item, "already_generated": item["asset_key"] in existing_keys} for item in image_tasks]
        return {
            "task_id": task_id,
            "image_count": len(preview),
            "already_generated": len(existing_keys),
            "next_batch": min(body.max_new_images, max(0, len(preview) - len(existing_keys))),
            "images": preview,
        }

    @app.post("/tasks/{task_id}/image-generate")
    def generate_task_images(task_id: str, body: ImageBatchRequest):
        """分批生成角色和场景参考图，成功一张就立即保存并落库。"""
        if body.confirm_paid is not True:
            raise HTTPException(status_code=400, detail="请将 confirm_paid 设为 true，确认图片生成可能产生费用")
        with image_generate_lock:
            record, image_tasks = build_image_plan(task_id)
            existing = record.state.get("image_assets", [])
            if not isinstance(existing, list):
                raise HTTPException(status_code=409, detail="任务中的 image_assets 数据格式无效")
            assets = [item for item in existing if isinstance(item, dict)]
            planned_keys = {item["asset_key"] for item in image_tasks}
            existing_keys = {item.get("asset_key") for item in assets if item.get("asset_key") in planned_keys}
            pending = [item for item in image_tasks if item["asset_key"] not in existing_keys]
            client = get_image_provider_client()
            output_root = (
                agent.asset_store.root
                if agent.asset_store is not None
                else Path(__file__).resolve().parents[2] / "04_Data" / "runtime" / "assets"
            )
            output_dir = output_root / task_id / "reference_images"
            state = dict(record.state)
            new_count = 0
            try:
                for item in pending[: body.max_new_images]:
                    generated = client.generate_image(item["prompt"], allow_paid=True)
                    local_file = client.save_result(generated, output_dir, item["asset_key"])
                    assets.append(
                        {
                            "asset_key": item["asset_key"],
                            "kind": item["kind"],
                            "label": item["label"],
                            "status": "saved",
                            "local_file": str(local_file),
                            "provider_model": str(generated.get("model") or "configured-provider"),
                        }
                    )
                    new_count += 1
                    existing_keys.add(item["asset_key"])
                    state["image_assets"] = assets
                    agent._save(record, record.status, state)
            except (ValueError, TypeError, PermissionError, RuntimeError) as exc:
                state["image_assets"] = assets
                if new_count:
                    agent._record_event(
                        task_id,
                        state,
                        "image_assets_partial",
                        {"new_count": new_count, "completed": len(assets), "error": str(exc)},
                    )
                    agent._save(record, record.status, state)
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            remaining = len(planned_keys - existing_keys)
            state["image_assets"] = assets
            agent._record_event(
                task_id,
                state,
                "image_assets_generated",
                {"new_count": new_count, "completed": len(assets), "remaining": remaining},
            )
            saved = agent._save(record, record.status, state)
            return {
                "task_id": task_id,
                "new_count": new_count,
                "remaining": remaining,
                "assets": saved.state["image_assets"],
            }

    @app.get("/tasks/{task_id}/image-assets")
    def list_task_image_assets(task_id: str):
        record = agent.store.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        assets = record.state.get("image_assets", [])
        if not isinstance(assets, list):
            raise HTTPException(status_code=409, detail="任务中的 image_assets 数据格式无效")
        return {"task_id": task_id, "assets": [item for item in assets if isinstance(item, dict)]}

    @app.get("/tasks/{task_id}/image-assets/{asset_key}")
    def download_task_image_asset(task_id: str, asset_key: str):
        """只读返回当前任务已保存的单张图片，禁止借此访问其他路径。"""
        record = agent.store.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        assets = record.state.get("image_assets", [])
        if not isinstance(assets, list):
            raise HTTPException(status_code=409, detail="任务中的 image_assets 数据格式无效")
        matched = next(
            (
                item
                for item in assets
                if isinstance(item, dict) and item.get("asset_key") == asset_key and item.get("status") == "saved"
            ),
            None,
        )
        if matched is None:
            raise HTTPException(status_code=404, detail="图片资产不存在")
        local_file = matched.get("local_file")
        if not isinstance(local_file, str) or not local_file.strip():
            raise HTTPException(status_code=409, detail="图片资产缺少本地文件路径")
        output_root = (
            agent.asset_store.root
            if agent.asset_store is not None
            else Path(__file__).resolve().parents[2] / "04_Data" / "runtime" / "assets"
        )
        task_asset_dir = (output_root / task_id / "reference_images").resolve()
        candidate = Path(local_file).expanduser().resolve()
        try:
            candidate.relative_to(task_asset_dir)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="图片资产路径不属于当前任务目录") from exc
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="图片文件不存在")
        return FileResponse(candidate)

    def build_artclaw_reference_preview(task_id: str, body: ArtClawBatchRequest):
        record = agent.store.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        storyboard = record.state.get("stage_results", {}).get("plan", {}).get("storyboard", [])
        if not isinstance(storyboard, list) or not storyboard:
            raise HTTPException(status_code=409, detail="任务尚未完成分镜规划")

        default_references = normalize_reference_urls(body.reference_urls)
        shot_references: dict[int, list[str]] = {}
        for shot_index, reference_urls in body.shot_reference_urls.items():
            if shot_index < 1 or shot_index > len(storyboard):
                raise ValueError(f"参考图映射包含不存在的分镜编号: {shot_index}")
            shot_references[shot_index] = normalize_reference_urls(reference_urls)

        references_by_index: dict[int, list[str]] = {}
        preview: list[dict[str, Any]] = []
        for shot_index, shot in enumerate(storyboard, start=1):
            if not isinstance(shot, dict):
                raise ValueError(f"第 {shot_index} 个分镜必须是对象")
            prompt = str(shot.get("prompt") or shot.get("shot") or "").strip()
            if not prompt:
                raise ValueError(f"第 {shot_index} 个分镜缺少可提交的提示词")
            has_shot_mapping = shot_index in shot_references
            references = shot_references[shot_index] if has_shot_mapping else default_references
            references_by_index[shot_index] = references
            submitted_prompt = add_reference_instructions(prompt, len(references))
            preview.append(
                {
                    "shot_index": shot_index,
                    "scene": shot.get("scene", ""),
                    "prompt": submitted_prompt,
                    "reference_count": len(references),
                    "reference_source": "shot" if has_shot_mapping else ("default" if references else "none"),
                }
            )
        return record, storyboard, references_by_index, preview

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

    @app.post("/tasks/{task_id}/artclaw-preview")
    def preview_task_storyboard_for_artclaw(task_id: str, body: ArtClawBatchRequest):
        """付费提交前检查逐分镜参考图选择，不调用 ArtClaw。"""
        try:
            record, _storyboard, _references_by_index, preview = build_artclaw_reference_preview(task_id, body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        submitted_by_index = {
            item.get("shot_index"): item for item in record.state.get("artclaw_jobs", []) if isinstance(item, dict)
        }
        shots = []
        for item in preview:
            submitted = submitted_by_index.get(item["shot_index"])
            if submitted is None:
                shots.append({**item, "already_submitted": False})
                continue
            shots.append(
                {
                    **item,
                    "reference_count": submitted.get("reference_count", item["reference_count"]),
                    "reference_source": submitted.get("reference_source", item["reference_source"]),
                    "already_submitted": True,
                }
            )
        return {"task_id": task_id, "shot_count": len(shots), "shots": shots}

    @app.post("/tasks/{task_id}/artclaw-submit")
    def submit_task_storyboard_to_artclaw(task_id: str, body: ArtClawBatchRequest):
        """把已完成的规划阶段分镜批量提交到 ArtClaw。"""
        if body.confirm_paid is not True:
            raise HTTPException(status_code=400, detail="请将 confirm_paid 设为 true，确认可能产生费用")
        with artclaw_submit_lock:
            try:
                record, storyboard, references_by_index, reference_preview = build_artclaw_reference_preview(task_id, body)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            existing = record.state.get("artclaw_jobs", [])
            existing_by_index = {item.get("shot_index"): item for item in existing if isinstance(item, dict)}
            client = get_artclaw_client()
            submitted = list(existing_by_index.values())
            new_count = 0
            state = dict(record.state)
            try:
                for index, shot in enumerate(storyboard, start=1):
                    if index in existing_by_index:
                        continue
                    if new_count >= body.max_new_jobs:
                        break
                    if not isinstance(shot, dict):
                        raise ValueError("分镜项必须是对象")
                    prompt = reference_preview[index - 1]["prompt"]
                    result = client.submit_video(
                        prompt,
                        references_by_index[index],
                        duration_seconds=body.duration_seconds,
                        allow_paid=True,
                    )
                    preview_item = reference_preview[index - 1]
                    submitted.append(
                        {
                            "shot_index": index,
                            "scene": shot.get("scene", ""),
                            "job_id": result.get("job_id"),
                            "status": result.get("status", "pending"),
                            "reference_count": preview_item["reference_count"],
                            "reference_source": preview_item["reference_source"],
                        }
                    )
                    new_count += 1
                    state["artclaw_jobs"] = submitted
                    agent._save(record, record.status, state)
            except (ValueError, RuntimeError) as exc:
                # 先落库已成功提交的分镜，重试时可复用任务编号，避免重复计费。
                state["artclaw_jobs"] = submitted
                if submitted:
                    agent._record_event(task_id, state, "artclaw_jobs_partial", {"count": len(submitted), "error": str(exc)})
                    agent._save(record, record.status, state)
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            state["artclaw_jobs"] = submitted
            remaining = max(0, len(storyboard) - len(submitted))
            agent._record_event(task_id, state, "artclaw_jobs_submitted", {"new_count": new_count, "remaining": remaining})
            saved = agent._save(record, record.status, state)
            return {"task_id": task_id, "new_count": new_count, "remaining": remaining, "jobs": saved.state["artclaw_jobs"]}

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
        asset_root = agent.asset_store.root if agent.asset_store is not None else Path(__file__).resolve().parents[2] / "04_Data" / "runtime" / "assets"
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
            asset_root = agent.asset_store.root if agent.asset_store is not None else Path(__file__).resolve().parents[2] / "04_Data" / "runtime" / "assets"
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
        model_config = getattr(getattr(agent, "model", None), "client", None)
        model_config = getattr(model_config, "config", None)
        image_key_env = os.getenv("IMAGE_API_KEY_ENV", "IMAGE_API_KEY")
        return {
            "status": "ok",
            "service": "multimodal-creative-agent",
            "model_provider": getattr(agent, "model_provider", "offline"),
            "model_name": getattr(model_config, "model", "deterministic-offline"),
            "artclaw_configured": bool(os.getenv("ARTCLAW_API_KEY_ACCOUNT_A") or os.getenv("ARTCLAW_API_KEY")),
            "image_provider_configured": bool(os.getenv("IMAGE_API_BASE_URL") and os.getenv(image_key_env)),
        }

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
