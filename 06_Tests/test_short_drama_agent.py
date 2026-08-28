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
from integrations.artclaw import ArtClawClient, ArtClawConfig
from integrations.deepseek import DeepSeekClient, DeepSeekConfig, DeepSeekModel
from integrations.redis_backend import _redis_client
from short_drama_agent import create_fastapi_app
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


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        import json

        return json.dumps(self.payload).encode("utf-8")


class FakeOpener:
    def __init__(self):
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        return FakeResponse({"job_id": "job-demo"})


class DeepSeekFakeOpener:
    def __init__(self):
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        return FakeResponse({"choices": [{"message": {"content": '{"intent":"测试需求","content_type":"short_drama","constraints":[]}'}}]})


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

    def test_artclaw_client_blocks_paid_submit_by_default(self):
        import os

        opener = FakeOpener()
        os.environ["ARTCLAW_TEST_KEY"] = "test-only-key"
        client = ArtClawClient(ArtClawConfig(api_key_env="ARTCLAW_TEST_KEY"), opener=opener)
        with self.assertRaises(PermissionError):
            client.submit_video("生成一个镜头")
        self.assertEqual(opener.calls, [])
        result = client.submit_video("生成一个镜头", duration_seconds=4, allow_paid=True)
        self.assertEqual(result["job_id"], "job-demo")
        self.assertEqual(len(opener.calls), 1)
        del os.environ["ARTCLAW_TEST_KEY"]

    def test_artclaw_config_uses_low_cost_defaults(self):
        config = ArtClawConfig()
        self.assertEqual(config.resolution, "480p")
        self.assertFalse(config.generate_audio)
        self.assertEqual(config.aspect_ratio, "9:16")

    def test_deepseek_model_parses_structured_json(self):
        import os

        old = os.environ.get("DEEPSEEK_TEST_KEY")
        os.environ["DEEPSEEK_TEST_KEY"] = "test-only-key"
        try:
            client = DeepSeekClient(DeepSeekConfig(api_key_env="DEEPSEEK_TEST_KEY"), opener=DeepSeekFakeOpener())
            result = DeepSeekModel(client).generate("analyze", {"request": "测试需求", "constraints": []})
            self.assertEqual(result["intent"], "测试需求")
        finally:
            if old is None:
                os.environ.pop("DEEPSEEK_TEST_KEY", None)
            else:
                os.environ["DEEPSEEK_TEST_KEY"] = old

    def test_fastapi_routes_are_registered_without_external_services(self):
        agent = ShortDramaAgent(store=TaskStore())
        app = create_fastapi_app(agent)
        paths = {route.path for route in app.routes}
        self.assertIn("/health", paths)
        self.assertIn("/tasks/{task_id}/events", paths)
        self.assertIn("/ws/tasks/{task_id}", paths)
        self.assertIn("/artclaw/videos", paths)
        self.assertIn("/tasks/{task_id}/artclaw-submit", paths)
        self.assertIn("/tasks/{task_id}/artclaw-status", paths)
        self.assertIn("/tasks/{task_id}/artclaw-download", paths)
        health = next(route for route in app.routes if route.path == "/health")
        self.assertEqual(health.endpoint()["status"], "ok")

    def test_redis_adapter_reports_missing_configuration(self):
        import os

        old = os.environ.pop("REDIS_URL", None)
        try:
            with self.assertRaises(RuntimeError):
                _redis_client()
        finally:
            if old is not None:
                os.environ["REDIS_URL"] = old

    def test_celery_factory_reports_missing_configuration(self):
        import os

        old_broker = os.environ.pop("CELERY_BROKER_URL", None)
        old_redis = os.environ.pop("REDIS_URL", None)
        try:
            from celery_worker import create_celery_app

            with self.assertRaises(RuntimeError):
                create_celery_app()
        finally:
            if old_broker is not None:
                os.environ["CELERY_BROKER_URL"] = old_broker
            if old_redis is not None:
                os.environ["REDIS_URL"] = old_redis


if __name__ == "__main__":
    unittest.main()
