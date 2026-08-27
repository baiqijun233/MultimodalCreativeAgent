"""ArtClaw HTTP client with explicit protection against accidental paid jobs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ArtClawConfig:
    base_url: str = "https://artclaw.com/api/v1"
    model: str = "doubao-seedance-2-0-260128"
    aspect_ratio: str = "9:16"
    resolution: str = "480p"
    generate_audio: bool = False
    api_key_env: str = "ARTCLAW_API_KEY_ACCOUNT_A"
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "ArtClawConfig":
        timeout = os.getenv("ARTCLAW_TIMEOUT_SECONDS", "30")
        try:
            timeout_value = float(timeout)
        except ValueError as exc:
            raise ValueError("ARTCLAW_TIMEOUT_SECONDS 必须是数字") from exc
        if timeout_value <= 0:
            raise ValueError("ARTCLAW_TIMEOUT_SECONDS 必须大于 0")
        generate_audio = os.getenv("ARTCLAW_GENERATE_AUDIO", "false").strip().lower()
        if generate_audio not in {"true", "false", "1", "0", "yes", "no"}:
            raise ValueError("ARTCLAW_GENERATE_AUDIO 必须是 true 或 false")
        return cls(
            base_url=os.getenv("ARTCLAW_BASE_URL", cls.base_url).rstrip("/"),
            model=os.getenv("ARTCLAW_MODEL", cls.model),
            aspect_ratio=os.getenv("ARTCLAW_ASPECT_RATIO", cls.aspect_ratio),
            resolution=os.getenv("ARTCLAW_RESOLUTION", cls.resolution),
            generate_audio=generate_audio in {"true", "1", "yes"},
            api_key_env=os.getenv("ARTCLAW_API_KEY_ENV", cls.api_key_env),
            timeout_seconds=timeout_value,
        )


class ArtClawClient:
    def __init__(self, config: ArtClawConfig | None = None, opener: Any | None = None) -> None:
        self.config = config or ArtClawConfig.from_env()
        self._opener = opener or urlopen

    def _api_key(self) -> str:
        key = os.getenv(self.config.api_key_env) or os.getenv("ARTCLAW_API_KEY")
        if not key or not key.strip():
            raise RuntimeError(f"未找到 ArtClaw 密钥，请设置环境变量 {self.config.api_key_env}")
        return key.strip()

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if not path.startswith("/"):
            raise ValueError("ArtClaw API 路径必须以 / 开头")
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self.config.base_url}{path}",
            data=payload,
            method=method.upper(),
            headers={"X-API-KEY": self._api_key(), "Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with self._opener(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"ArtClaw 请求失败（HTTP {exc.code}）: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"ArtClaw 网络连接失败: {exc.reason}") from exc
        try:
            result = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError("ArtClaw 返回内容不是合法 JSON") from exc
        if not isinstance(result, dict):
            raise TypeError("ArtClaw 返回结果必须是对象")
        return result

    def account_info(self) -> dict[str, Any]:
        return self._request("GET", "/account/info")

    def submit_video(self, prompt: str, reference_urls: list[str] | None = None, *, duration_seconds: int = 4, allow_paid: bool = False) -> dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt 必须是非空字符串")
        if not isinstance(duration_seconds, int) or not 4 <= duration_seconds <= 15:
            raise ValueError("duration_seconds 必须是 4 到 15 的整数")
        references = [] if reference_urls is None else reference_urls
        if not isinstance(references, list) or any(not isinstance(url, str) or not url.strip() for url in references):
            raise ValueError("reference_urls 必须是非空字符串列表")
        if len(references) > 9:
            raise ValueError("reference_urls 最多 9 项")
        if self.config.aspect_ratio not in {"1:1", "4:3", "3:4", "16:9", "9:16"}:
            raise ValueError("aspect_ratio 必须是支持的标准画幅")
        if self.config.resolution not in {"480p", "720p", "1080p"}:
            raise ValueError("resolution 必须是 480p、720p 或 1080p")
        if not allow_paid:
            raise PermissionError("已阻止可能产生费用的 ArtClaw 提交；显式传入 allow_paid=True 后才会提交")
        return self._request(
            "POST",
            "/generate/video",
            {
                "model": self.config.model,
                "prompt": prompt.strip(),
                "reference_urls": references,
                "duration": duration_seconds,
                "aspect_ratio": self.config.aspect_ratio,
                "resolution": self.config.resolution,
                "generate_audio": self.config.generate_audio,
                "online_search": False,
            },
        )

    def get_job(self, job_id: str) -> dict[str, Any]:
        if not isinstance(job_id, str) or not job_id.strip():
            raise ValueError("job_id 必须是非空字符串")
        return self._request("GET", f"/jobs/{job_id.strip()}")
