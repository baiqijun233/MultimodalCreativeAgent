"""Run one complete local creative-agent task from PowerShell."""

from __future__ import annotations

import argparse
from pathlib import Path

from async_runner import AsyncTaskRunner
from common.assets import LocalAssetStore
from common.storage import TaskStore, record_to_dict
from short_drama_agent import ShortDramaAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="本地运行 AI 多模态创作 Agent 演示")
    parser.add_argument("--request", default="生成一段包含角色、分镜和多模态素材的短剧")
    parser.add_argument("--workdir", type=Path, default=Path(".local_demo"))
    args = parser.parse_args()
    workdir = args.workdir.expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    store = TaskStore(workdir / "tasks.db")
    agent = ShortDramaAgent(store=store, asset_store=LocalAssetStore(workdir / "assets"))
    runner = AsyncTaskRunner(agent, max_workers=1)
    try:
        created = runner.submit(args.request, ["角色一致", "结构化输出"])
        result = runner.result(created.task_id, timeout=30)
        print(record_to_dict(result))
    finally:
        runner.close()
        store.close()


if __name__ == "__main__":
    main()
