"""OpenAI-compatible image generation client with explicit paid-call protection."""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_RESPONSE_BYTES = 40 * 1024 * 1024


@dataclass(frozen=True)
class ImageProviderConfig:
    """通过环境变量连接兼容 ``/images/generations`` 的图片服务。"""

    base_url: str = ""
    model: str = "gpt-image-2"
    size: str = "1024x1024"
    api_key_env: str = "IMAGE_API_KEY"
    timeout_seconds: float = 120.0

    @classmethod
    def from_env(cls) -> "ImageProviderConfig":
        timeout = os.getenv("IMAGE_API_TIMEOUT_SECONDS", "120")
        try:
            timeout_value = float(timeout)
        except ValueError as exc:
            raise ValueError("IMAGE_API_TIMEOUT_SECONDS 必须是数字") from exc
        if timeout_value <= 0:
            raise ValueError("IMAGE_API_TIMEOUT_SECONDS 必须大于 0")
        return cls(
            base_url=os.getenv("IMAGE_API_BASE_URL", "").strip().rstrip("/"),
            model=os.getenv("IMAGE_API_MODEL", cls.model).strip(),
            size=os.getenv("IMAGE_API_SIZE", cls.size).strip(),
            api_key_env=os.getenv("IMAGE_API_KEY_ENV", cls.api_key_env).strip(),
            timeout_seconds=timeout_value,
        )


class ImageProviderClient:
    """生成单张图片并安全保存；默认绝不发起可能计费的请求。"""

    def __init__(self, config: ImageProviderConfig | None = None, opener: Any | None = None) -> None:
        self.config = config or ImageProviderConfig.from_env()
        self._opener = opener or urlopen

    def _api_key(self) -> str:
        key = os.getenv(self.config.api_key_env)
        if not key or not key.strip():
            raise RuntimeError(f"未找到图片服务密钥，请设置环境变量 {self.config.api_key_env}")
        return key.strip()

    def _endpoint(self) -> str:
        base_url = self.config.base_url.strip().rstrip("/")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("未配置有效的 IMAGE_API_BASE_URL；应为 http 或 https 地址")
        if not self.config.model:
            raise RuntimeError("IMAGE_API_MODEL 不能为空")
        if not re.fullmatch(r"\d{2,5}x\d{2,5}", self.config.size):
            raise ValueError("IMAGE_API_SIZE 必须使用 宽x高 格式，例如 1024x1024")
        return f"{base_url}/images/generations"

    def generate_image(self, prompt: str, *, allow_paid: bool = False) -> dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt 必须是非空字符串")
        if len(prompt) > 10000:
            raise ValueError("prompt 最多 10000 个字符")
        if not allow_paid:
            raise PermissionError("已阻止可能产生费用的图片生成；显式传入 allow_paid=True 后才会提交")

        body = json.dumps(
            {"model": self.config.model, "prompt": prompt.strip(), "size": self.config.size, "n": 1},
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            self._endpoint(),
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key()}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._opener(request, timeout=self.config.timeout_seconds) as response:
                raw = self._read_limited(response, MAX_RESPONSE_BYTES)
        except HTTPError as exc:
            detail = exc.read(1000).decode("utf-8", errors="replace")
            raise RuntimeError(f"图片服务请求失败（HTTP {exc.code}）: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", str(exc))
            raise RuntimeError(f"图片服务网络连接失败: {reason}") from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("图片服务返回内容不是合法 JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("图片服务返回结果必须是对象")
        data = payload.get("data")
        first = data[0] if isinstance(data, list) and data else None
        if not isinstance(first, dict):
            raise RuntimeError("图片服务返回结果缺少 data[0]")
        b64_json = first.get("b64_json")
        remote_url = first.get("url")
        if not isinstance(b64_json, str) and not isinstance(remote_url, str):
            raise RuntimeError("图片服务结果既没有 b64_json，也没有可下载的 url")
        return {
            "b64_json": b64_json if isinstance(b64_json, str) else None,
            "url": remote_url.strip() if isinstance(remote_url, str) else None,
            "model": str(payload.get("model") or self.config.model),
        }

    def save_result(self, result: dict[str, Any], output_dir: str | Path, filename_stem: str) -> Path:
        if not isinstance(result, dict):
            raise TypeError("result 必须是对象")
        safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "-", str(filename_stem).strip()).strip("-")
        if not safe_stem:
            raise ValueError("filename_stem 必须包含可用字符")
        target_dir = Path(output_dir).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        encoded = result.get("b64_json")
        if isinstance(encoded, str) and encoded:
            try:
                image_bytes = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise RuntimeError("图片服务返回的 Base64 数据无效") from exc
        else:
            image_bytes = self._download_public_image(result.get("url"))

        if not image_bytes:
            raise RuntimeError("图片生成结果为空")
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise RuntimeError("图片超过 25 MB 安全上限")
        extension = self._detect_extension(image_bytes)
        target = target_dir / f"{safe_stem}{extension}"
        temporary = target_dir / f".{safe_stem}.tmp"
        temporary.write_bytes(image_bytes)
        temporary.replace(target)
        return target

    def _download_public_image(self, value: Any) -> bytes:
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError("图片服务结果没有可保存的图片数据")
        url = value.strip()
        parsed = urlparse(url)
        hostname = parsed.hostname
        is_private = hostname in {"localhost", "127.0.0.1", "::1"} or bool(hostname and hostname.endswith(".local"))
        if hostname and not is_private:
            try:
                is_private = not ip_address(hostname).is_global
            except ValueError:
                pass
        if parsed.scheme != "https" or not parsed.netloc or is_private:
            raise RuntimeError("图片下载地址必须是公网 HTTPS 地址")
        request = Request(url, headers={"Accept": "image/*"})
        try:
            with self._opener(request, timeout=self.config.timeout_seconds) as response:
                return self._read_limited(response, MAX_IMAGE_BYTES)
        except HTTPError as exc:
            raise RuntimeError(f"图片下载失败（HTTP {exc.code}）") from exc
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", str(exc))
            raise RuntimeError(f"图片下载网络连接失败: {reason}") from exc

    @staticmethod
    def _read_limited(response: Any, maximum: int) -> bytes:
        try:
            data = response.read(maximum + 1)
        except TypeError:
            data = response.read()
        if len(data) > maximum:
            raise RuntimeError("图片服务响应超过安全大小上限")
        return data

    @staticmethod
    def _detect_extension(data: bytes) -> str:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if data.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
            return ".webp"
        raise RuntimeError("图片格式无效；仅接受 PNG、JPEG 或 WebP")
