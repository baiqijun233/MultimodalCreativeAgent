"""Local asset archive used as an offline replacement for object storage."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


class LocalAssetStore:
    """Persist generated asset metadata so a task can be reviewed later."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def archive_jobs(self, task_id: str, asset_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id 必须是非空字符串")
        if not isinstance(asset_jobs, list):
            raise ValueError("asset_jobs 必须是列表")
        task_dir = self.root / task_id.strip()
        task_dir.mkdir(parents=True, exist_ok=True)
        archived: list[dict[str, Any]] = []
        for job in asset_jobs:
            if not isinstance(job, dict) or not isinstance(job.get("job_id"), str) or not isinstance(job.get("type"), str):
                raise ValueError("每个资产任务必须包含字符串 job_id 和 type")
            metadata = {**job, "status": "archived", "storage": "local"}
            metadata_path = task_dir / f"{job['job_id']}.json"
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            archived.append({**metadata, "uri": metadata_path.as_uri()})
        return archived

    def list_task_directories(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(item.name for item in self.root.iterdir() if item.is_dir())

    def remove_task_directory(self, task_id: str) -> bool:
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id 必须是非空字符串")
        target = (self.root / task_id.strip()).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("资产目录不属于当前资产根目录") from exc
        if target == self.root or not target.is_dir():
            return False
        shutil.rmtree(target)
        return True
