"""DeepSeek OpenAI-compatible client and model adapter."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class DeepSeekConfig:
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    api_key_env: str = "DEEPSEEK_API_KEY"
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> "DeepSeekConfig":
        timeout_text = os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "60")
        try:
            timeout = float(timeout_text)
        except ValueError as exc:
            raise ValueError("DEEPSEEK_TIMEOUT_SECONDS 必须是数字") from exc
        if timeout <= 0:
            raise ValueError("DEEPSEEK_TIMEOUT_SECONDS 必须大于 0")
        return cls(
            base_url=os.getenv("DEEPSEEK_BASE_URL", cls.base_url).rstrip("/"),
            model=os.getenv("DEEPSEEK_MODEL", cls.model),
            api_key_env=os.getenv("DEEPSEEK_API_KEY_ENV", cls.api_key_env),
            timeout_seconds=timeout,
        )


class DeepSeekClient:
    def __init__(self, config: DeepSeekConfig | None = None, opener: Any | None = None) -> None:
        self.config = config or DeepSeekConfig.from_env()
        self._opener = opener or urlopen

    def _api_key(self) -> str:
        key = os.getenv(self.config.api_key_env)
        if not key or not key.strip():
            raise RuntimeError(f"未找到 DeepSeek 密钥，请设置环境变量 {self.config.api_key_env}")
        return key.strip()

    def chat_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError("system_prompt 必须是非空字符串")
        if not isinstance(user_payload, dict):
            raise TypeError("user_payload 必须是对象")
        body = {
            "model": self.config.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self.config.base_url}/chat/completions",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key()}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._opener(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"DeepSeek 请求失败（HTTP {exc.code}）: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", str(exc))
            raise RuntimeError(f"DeepSeek 网络连接失败: {reason}") from exc
        try:
            response_data = json.loads(raw) if raw else {}
            content = response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("DeepSeek 返回结果缺少合法 choices.message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("DeepSeek 返回内容为空")
        text = content.strip()
        if text.startswith("```"):
            text = text.removeprefix("```").removeprefix("json").removesuffix("```").strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("DeepSeek 返回内容不是合法 JSON") from exc
        if not isinstance(result, dict):
            raise TypeError("DeepSeek 结构化结果必须是对象")
        return result


class DeepSeekModel:
    """将需求解析和分镜规划交给 DeepSeek，其余阶段复用本地确定性逻辑。"""

    def __init__(self, client: DeepSeekClient | None = None) -> None:
        self.client = client or DeepSeekClient()

    def generate(self, stage: str, payload: dict[str, Any]) -> dict[str, Any]:
        if stage not in {"analyze", "plan"}:
            from short_drama_agent import DeterministicModel

            return DeterministicModel().generate(stage, payload)
        prompt = (
            "你是短剧多模态创作规划器。只返回 JSON 对象，不要 Markdown。"
            "analyze 阶段返回 intent、content_type、constraints；"
            "plan 阶段返回 characters、scenes、storyboard、asset_types。"
            "plan 阶段 scenes 和 storyboard 数量必须完全相等，asset_types 只能从 image、video、audio 中选择。"
            "storyboard 必须是数组，每项包含 scene、shot、prompt，prompt 要能独立用于视频生成，"
            "并写清角色外观、服装、场景、动作、镜头、光线、画幅和连续性约束。"
        )
        result = self.client.chat_json(prompt, {"stage": stage, "payload": payload})
        if stage == "analyze" and not all(name in result for name in ("intent", "content_type", "constraints")):
            raise RuntimeError("DeepSeek analyze 结果缺少必要字段")
        if stage == "analyze":
            if not isinstance(result["intent"], str) or not result["intent"].strip():
                raise RuntimeError("DeepSeek analyze 的 intent 必须是非空字符串")
            if not isinstance(result["content_type"], str) or not result["content_type"].strip():
                raise RuntimeError("DeepSeek analyze 的 content_type 必须是非空字符串")
            if not isinstance(result["constraints"], list) or not all(isinstance(item, str) for item in result["constraints"]):
                raise RuntimeError("DeepSeek analyze 的 constraints 必须是字符串数组")
        if stage == "plan" and not all(name in result for name in ("characters", "scenes", "storyboard", "asset_types")):
            raise RuntimeError("DeepSeek plan 结果缺少必要字段")
        if stage == "plan":
            if not all(isinstance(result[name], list) for name in ("characters", "scenes", "storyboard", "asset_types")):
                raise RuntimeError("DeepSeek plan 字段类型不正确")
            if not all(result[name] for name in ("characters", "scenes", "storyboard", "asset_types")):
                raise RuntimeError("DeepSeek plan 结果不能为空")
            if not all(isinstance(item, dict) and str(item.get("name", "")).strip() for item in result["characters"]):
                raise RuntimeError("DeepSeek plan 的角色项必须包含非空 name")
            if not all(isinstance(item, str) and item.strip() for item in result["scenes"]):
                raise RuntimeError("DeepSeek plan 的场景必须是非空字符串")
            if len(result["scenes"]) != len(result["storyboard"]):
                raise RuntimeError("DeepSeek plan 场景数与分镜数不一致")
            required_shot_fields = ("scene", "shot", "prompt")
            for item in result["storyboard"]:
                if not isinstance(item, dict) or not all(
                    isinstance(item.get(name), str) and item[name].strip() for name in required_shot_fields
                ):
                    raise RuntimeError("DeepSeek plan 分镜项缺少非空字段 scene、shot 或 prompt")
            supported_asset_types = {"image", "video", "audio"}
            if not all(isinstance(item, str) and item in supported_asset_types for item in result["asset_types"]):
                raise RuntimeError("DeepSeek plan 包含不支持的素材类型")
        return result
