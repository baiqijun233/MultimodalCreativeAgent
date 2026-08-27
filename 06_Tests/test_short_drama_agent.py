import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "02_Source" / "multimodal_creative_agent"
sys.path.insert(0, str(SOURCE))

from common.storage import TaskStore
from common.assets import LocalAssetStore
from common.events import InMemoryEventBus
from async_runner import AsyncTaskRunner
from short_drama_agent import ShortDramaAgent


class FlakyModel:
    """第一次调用失败，第二次调用交给离线模型，验证重试链路。"""

    def __init__(self, fail_stage: str):
        self.fail_stage = fail_stage
        self.failed = False

    def generate(self, stage, payload):
        if stage == self.fail_stage and not self.failed:
            self.failed = True
            raise RuntimeError("模拟模型暂时不可用")
        from short_drama_agent import DeterministicModel

        return DeterministicModel().generate(stage, payload)


class AlwaysFailModel:
    def __init__(self, fail_stage: str):
        self.fail_stage = fail_stage

    def generate(self, stage, payload):
        if stage == self.fail_stage:
            raise RuntimeError("模拟阶段失败")
        from short_drama_agent import DeterministicModel

        return DeterministicModel().generate(stage, payload)


class ShortDramaAgentTests(unittest.TestCase):
    def test_state_machine_persists_result(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.db")
            agent = ShortDramaAgent(store=store)
            created = agent.create_task("生成一段多模态内容", ["角色一致", "结构化输出"])
            result = agent.run(created.task_id)
            self.assertEqual(result.status, "succeeded")
            self.assertEqual(result.state["result"]["status"], "ready")
            self.assertEqual(store.get(created.task_id).status, "succeeded")
            store.close()

    def test_rejects_empty_request(self):
        with self.assertRaises(ValueError):
            ShortDramaAgent().create_task(" ")

    def test_retry_is_recorded(self):
        store = TaskStore()
        agent = ShortDramaAgent(store=store, model=FlakyModel("plan"), max_retries=1)
        result = agent.run(agent.create_task("生成带角色和分镜的短剧").task_id)
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.state["attempts"]["plan"], 2)
        self.assertEqual(result.state["retry_log"][0]["stage"], "plan")
        store.close()

    def test_failed_stage_is_persisted_and_can_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.db")
            agent = ShortDramaAgent(store=store, model=AlwaysFailModel("assets"), max_retries=0)
            task_id = agent.create_task("生成图片、视频和配音素材").task_id
            with self.assertRaises(RuntimeError):
                agent.run(task_id)
            failed = store.get(task_id)
            self.assertEqual(failed.status, "failed")
            self.assertEqual(failed.state["current_stage"], "assets")
            self.assertIn("plan", failed.state["stage_results"])

            agent.model = __import__("short_drama_agent").DeterministicModel()
            resumed = agent.run(task_id)
            self.assertEqual(resumed.status, "succeeded")
            self.assertEqual(resumed.state["result"]["asset_count"], 3)
            store.close()

    def test_assets_are_archived_and_events_are_emitted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.db")
            bus = InMemoryEventBus()
            agent = ShortDramaAgent(
                store=store,
                asset_store=LocalAssetStore(Path(directory) / "assets"),
                event_bus=bus,
            )
            result = agent.run(agent.create_task("归档短剧图片、视频和音频").task_id)
            jobs = result.state["stage_results"]["assets"]["asset_jobs"]
            self.assertEqual({job["status"] for job in jobs}, {"archived"})
            self.assertTrue(all(job["uri"].startswith("file:") for job in jobs))
            event_types = [event["type"] for event in bus.list_events(result.task_id)]
            self.assertIn("stage_started", event_types)
            self.assertIn("task_succeeded", event_types)
            self.assertEqual(len(result.state["events"]), len(event_types))
            store.close()

    def test_async_runner_completes_task(self):
        store = TaskStore()
        agent = ShortDramaAgent(store=store)
        runner = AsyncTaskRunner(agent, max_workers=1)
        created = runner.submit("异步生成一段短剧")
        finished = runner.result(created.task_id, timeout=3)
        self.assertEqual(finished.status, "succeeded")
        runner.close()
        store.close()


if __name__ == "__main__":
    unittest.main()
