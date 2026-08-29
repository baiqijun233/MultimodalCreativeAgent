import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


class FakeResponseBytes:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


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


class FakeArtClawClient:
    submit_count = 0
    submissions = []

    def submit_video(self, prompt, reference_urls, *, duration_seconds, allow_paid):
        self.__class__.submit_count += 1
        self.__class__.submissions.append(
            {
                "prompt": prompt,
                "reference_urls": list(reference_urls),
                "duration_seconds": duration_seconds,
                "allow_paid": allow_paid,
            }
        )
        return {"job_id": f"job-{self.submit_count}", "status": "pending"}


class FakeImageProviderClient:
    generate_count = 0

    def generate_image(self, prompt, *, allow_paid):
        self.__class__.generate_count += 1
        return {"prompt": prompt, "sequence": self.generate_count, "allow_paid": allow_paid}

    def save_result(self, result, output_dir, filename_stem):
        target = Path(output_dir) / f"{filename_stem}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\x89PNG\r\n\x1a\n" + str(result["sequence"]).encode("ascii"))
        return target


class StaticDeepSeekClient:
    def __init__(self, result):
        self.result = result

    def chat_json(self, _prompt, _payload):
        return self.result


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
        self.assertEqual(opener.calls[0][0].get_header("User-agent"), "MultimodalCreativeAgent/1.0")
        del os.environ["ARTCLAW_TEST_KEY"]

    def test_artclaw_config_uses_low_cost_defaults(self):
        config = ArtClawConfig()
        self.assertEqual(config.resolution, "480p")
        self.assertFalse(config.generate_audio)
        self.assertEqual(config.aspect_ratio, "9:16")

    def test_image_provider_blocks_paid_request_by_default_and_saves_base64(self):
        import base64
        import os

        from integrations.image_provider import ImageProviderClient, ImageProviderConfig

        encoded = base64.b64encode(b"\x89PNG\r\n\x1a\nimage-data").decode("ascii")

        class ImageOpener(FakeOpener):
            def __call__(self, request, timeout):
                self.calls.append((request, timeout))
                return FakeResponse({"data": [{"b64_json": encoded}]})

        opener = ImageOpener()
        old = os.environ.get("IMAGE_TEST_KEY")
        os.environ["IMAGE_TEST_KEY"] = "test-only-key"
        try:
            config = ImageProviderConfig(base_url="https://images.example.com/v1", api_key_env="IMAGE_TEST_KEY")
            client = ImageProviderClient(config, opener=opener)
            with self.assertRaises(PermissionError):
                client.generate_image("生成角色设定图")
            self.assertEqual(opener.calls, [])
            result = client.generate_image("生成角色设定图", allow_paid=True)
            request, timeout = opener.calls[0]
            import json

            request_body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(request.full_url, "https://images.example.com/v1/images/generations")
            self.assertEqual(request_body["model"], "gpt-image-2")
            self.assertEqual(request_body["size"], "1024x1024")
            self.assertEqual(timeout, config.timeout_seconds)
            with tempfile.TemporaryDirectory() as directory:
                saved = client.save_result(result, directory, "character-1")
                self.assertTrue(saved.exists())
                self.assertTrue(saved.read_bytes().startswith(b"\x89PNG"))
        finally:
            if old is None:
                os.environ.pop("IMAGE_TEST_KEY", None)
            else:
                os.environ["IMAGE_TEST_KEY"] = old

    def test_artclaw_client_rejects_local_reference_path(self):
        import os

        opener = FakeOpener()
        old = os.environ.get("ARTCLAW_TEST_KEY")
        os.environ["ARTCLAW_TEST_KEY"] = "test-only-key"
        try:
            client = ArtClawClient(ArtClawConfig(api_key_env="ARTCLAW_TEST_KEY"), opener=opener)
            with self.assertRaisesRegex(ValueError, "远程服务无法读取本地参考图"):
                client.submit_video(
                    "生成一个镜头",
                    [r"E:\Agent\character.png"],
                    allow_paid=True,
                )
            self.assertEqual(opener.calls, [])
        finally:
            if old is None:
                os.environ.pop("ARTCLAW_TEST_KEY", None)
            else:
                os.environ["ARTCLAW_TEST_KEY"] = old

    def test_artclaw_download_uses_application_user_agent(self):
        import os

        class DownloadOpener:
            def __init__(self):
                self.request = None

            def __call__(self, request, timeout):
                self.request = request
                return FakeResponseBytes(b"video-bytes")

        opener = DownloadOpener()
        old = os.environ.get("ARTCLAW_TEST_KEY")
        os.environ["ARTCLAW_TEST_KEY"] = "test-only-key"
        try:
            client = ArtClawClient(ArtClawConfig(api_key_env="ARTCLAW_TEST_KEY"), opener=opener)
            with tempfile.TemporaryDirectory() as directory:
                path = client.download_result(
                    {"job_id": "job-download", "result": {"url": "https://assets.vicoo.ai/video.mp4"}},
                    directory,
                )
                self.assertTrue(path.exists())
                self.assertEqual(opener.request.get_header("User-agent"), "MultimodalCreativeAgent/1.0")
        finally:
            if old is None:
                os.environ.pop("ARTCLAW_TEST_KEY", None)
            else:
                os.environ["ARTCLAW_TEST_KEY"] = old

    def test_artclaw_download_route_exposes_stable_download_url(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("未安装 FastAPI TestClient 依赖")

        class FakeClient:
            def get_job(self, job_id):
                return {"job_id": job_id, "status": "success", "result": {"url": "https://assets.vicoo.ai/video.mp4"}}

            def download_result(self, _job, output_dir):
                target = Path(output_dir) / "artclaw_job-route.mp4"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"video-bytes")
                return target

        with tempfile.TemporaryDirectory() as directory:
            agent = ShortDramaAgent(store=TaskStore(Path(directory) / "tasks.db"), asset_store=LocalAssetStore(Path(directory) / "assets"))
            with patch("integrations.artclaw.ArtClawClient", FakeClient):
                response = TestClient(create_fastapi_app(agent)).post("/artclaw/videos/job-route/download")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["download_url"], "/artclaw/videos/job-route/download")
            agent.store.close()

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

    def test_runtime_can_explicitly_force_offline_model(self):
        import os
        from runtime import build_runtime_agent

        old_provider = os.environ.get("MODEL_PROVIDER")
        old_key = os.environ.get("DEEPSEEK_API_KEY")
        os.environ["MODEL_PROVIDER"] = "offline"
        os.environ["DEEPSEEK_API_KEY"] = "test-only-key"
        try:
            agent = build_runtime_agent()
            self.assertEqual(agent.model_provider, "offline")
            agent.store.close()
        finally:
            if old_provider is None:
                os.environ.pop("MODEL_PROVIDER", None)
            else:
                os.environ["MODEL_PROVIDER"] = old_provider
            if old_key is None:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            else:
                os.environ["DEEPSEEK_API_KEY"] = old_key

    def test_runtime_prefers_deepseek_by_default_when_key_exists(self):
        import os
        from runtime import build_runtime_agent

        with tempfile.TemporaryDirectory() as directory:
            overrides = {
                "MODEL_PROVIDER": None,
                "DEEPSEEK_API_KEY": "test-only-key",
                "TASK_DATABASE_PATH": str(Path(directory) / "tasks.db"),
                "ASSET_ROOT": str(Path(directory) / "assets"),
                "REDIS_URL": None,
            }
            original = {name: os.environ.get(name) for name in overrides}
            try:
                for name, value in overrides.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value
                agent = build_runtime_agent()
                self.assertEqual(agent.model_provider, "deepseek")
                self.assertIsInstance(agent.model, DeepSeekModel)
                agent.store.close()
            finally:
                for name, value in original.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value

    def test_deepseek_plan_rejects_mismatched_scene_count(self):
        result = {
            "characters": [{"name": "主角"}],
            "scenes": ["开场", "结尾"],
            "storyboard": [{"scene": "开场", "shot": "全景", "prompt": "主角走入房间"}],
            "asset_types": ["video"],
        }
        with self.assertRaisesRegex(RuntimeError, "场景数与分镜数不一致"):
            DeepSeekModel(StaticDeepSeekClient(result)).generate("plan", {})

    def test_deepseek_plan_accepts_structured_scene_objects_and_normalizes_names(self):
        result = {
            "characters": [{"name": "主角"}],
            "scenes": [{"name": "夜街", "location": "霓虹街道"}],
            "storyboard": [{"scene": "夜街", "shot": "全景", "prompt": "主角走过霓虹街道"}],
            "asset_types": ["image", "video"],
        }
        normalized = DeepSeekModel(StaticDeepSeekClient(result)).generate("plan", {})
        self.assertEqual(normalized["scenes"], ["夜街"])
        self.assertEqual(normalized["storyboard"][0]["scene"], "夜街")

    def test_deepseek_plan_accepts_single_asset_type_string(self):
        result = {
            "characters": [{"name": "主角"}],
            "scenes": ["夜街"],
            "storyboard": [{"scene": "夜街", "shot": "全景", "prompt": "主角走过街道"}],
            "asset_types": "video",
        }
        normalized = DeepSeekModel(StaticDeepSeekClient(result)).generate("plan", {})
        self.assertEqual(normalized["asset_types"], ["video"])

    def test_deepseek_plan_rejects_unsupported_asset_type(self):
        result = {
            "characters": [{"name": "主角"}],
            "scenes": ["开场"],
            "storyboard": [{"scene": "开场", "shot": "全景", "prompt": "主角走入房间"}],
            "asset_types": ["video", "subtitle"],
        }
        with self.assertRaisesRegex(RuntimeError, "包含不支持的素材类型"):
            DeepSeekModel(StaticDeepSeekClient(result)).generate("plan", {})

    def test_deepseek_plan_rejects_incomplete_storyboard_item(self):
        result = {
            "characters": [{"name": "主角"}],
            "scenes": ["开场"],
            "storyboard": [{"scene": "开场", "shot": "全景", "prompt": ""}],
            "asset_types": ["video"],
        }
        with self.assertRaisesRegex(RuntimeError, "分镜项缺少非空字段"):
            DeepSeekModel(StaticDeepSeekClient(result)).generate("plan", {})

    def test_deepseek_timeout_is_wrapped(self):
        import os
        from urllib.error import URLError

        class TimeoutOpener:
            def __call__(self, _request, timeout):
                raise URLError("timed out")

        old = os.environ.get("DEEPSEEK_TEST_KEY")
        os.environ["DEEPSEEK_TEST_KEY"] = "test-only-key"
        try:
            client = DeepSeekClient(DeepSeekConfig(api_key_env="DEEPSEEK_TEST_KEY"), opener=TimeoutOpener())
            with self.assertRaisesRegex(RuntimeError, "DeepSeek 网络连接失败"):
                client.chat_json("返回 JSON", {"stage": "analyze"})
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
        self.assertIn("/", paths)
        self.assertIn("/favicon.ico", paths)
        self.assertIn("/tasks", paths)
        self.assertIn("/maintenance/cleanup", paths)
        self.assertIn("/tasks/{task_id}/events", paths)
        self.assertIn("/ws/tasks/{task_id}", paths)
        self.assertIn("/artclaw/videos", paths)
        self.assertIn("/tasks/{task_id}/artclaw-preview", paths)
        self.assertIn("/tasks/{task_id}/artclaw-submit", paths)
        self.assertIn("/tasks/{task_id}/artclaw-status", paths)
        self.assertIn("/tasks/{task_id}/artclaw-download", paths)
        self.assertIn("/tasks/{task_id}/image-preview", paths)
        self.assertIn("/tasks/{task_id}/image-generate", paths)
        self.assertIn("/tasks/{task_id}/image-assets", paths)
        self.assertIn("/tasks/{task_id}/image-assets/{asset_key}", paths)
        health = next(route for route in app.routes if route.path == "/health")
        self.assertEqual(health.endpoint()["status"], "ok")
        self.assertIn(health.endpoint()["model_provider"], {"deepseek", "offline"})
        self.assertIn("model_name", health.endpoint())
        self.assertIn("artclaw_configured", health.endpoint())
        self.assertIn("image_provider_configured", health.endpoint())

    def test_artclaw_batch_submit_limits_and_reuses_jobs(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("未安装 FastAPI TestClient 依赖")
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.db")
            agent = ShortDramaAgent(store=store)
            task_id = agent.create_task("生成三段短剧分镜").task_id
            agent.run(task_id)
            FakeArtClawClient.submit_count = 0
            FakeArtClawClient.submissions = []
            with patch("integrations.artclaw.ArtClawClient", FakeArtClawClient):
                client = TestClient(create_fastapi_app(agent))
                first = client.post(
                    f"/tasks/{task_id}/artclaw-submit",
                    json={"confirm_paid": True, "max_new_jobs": 2},
                )
                self.assertEqual(first.status_code, 200)
                self.assertEqual(first.json()["new_count"], 2)
                self.assertEqual(first.json()["remaining"], 1)
                second = client.post(
                    f"/tasks/{task_id}/artclaw-submit",
                    json={"confirm_paid": True, "max_new_jobs": 2},
                )
                self.assertEqual(second.status_code, 200)
                self.assertEqual(second.json()["new_count"], 1)
                self.assertEqual(second.json()["remaining"], 0)
                third = client.post(
                    f"/tasks/{task_id}/artclaw-submit",
                    json={"confirm_paid": True, "max_new_jobs": 2},
                )
                self.assertEqual(third.status_code, 200)
                self.assertEqual(third.json()["new_count"], 0)
                self.assertEqual(FakeArtClawClient.submit_count, 3)
            store.close()

    def test_artclaw_batch_uses_shot_specific_references(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("未安装 FastAPI TestClient 依赖")
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.db")
            agent = ShortDramaAgent(store=store)
            task_id = agent.create_task("生成三段角色连续的短剧分镜").task_id
            agent.run(task_id)
            FakeArtClawClient.submit_count = 0
            FakeArtClawClient.submissions = []
            body = {
                "reference_urls": ["https://cdn.example.com/default-room.jpg"],
                "shot_reference_urls": {
                    "1": ["https://cdn.example.com/hero-front.jpg"],
                    "3": ["https://cdn.example.com/hero-ending.jpg"],
                },
                "max_new_jobs": 3,
            }
            with patch("integrations.artclaw.ArtClawClient", FakeArtClawClient):
                client = TestClient(create_fastapi_app(agent))
                preview = client.post(f"/tasks/{task_id}/artclaw-preview", json=body)
                self.assertEqual(preview.status_code, 200)
                self.assertEqual(FakeArtClawClient.submissions, [])
                self.assertEqual(
                    [item["reference_source"] for item in preview.json()["shots"]],
                    ["shot", "default", "shot"],
                )

                paid_body = {**body, "confirm_paid": True}
                submitted = client.post(f"/tasks/{task_id}/artclaw-submit", json=paid_body)
                self.assertEqual(submitted.status_code, 200)
                self.assertEqual(
                    [item["reference_urls"] for item in FakeArtClawClient.submissions],
                    [
                        ["https://cdn.example.com/hero-front.jpg"],
                        ["https://cdn.example.com/default-room.jpg"],
                        ["https://cdn.example.com/hero-ending.jpg"],
                    ],
                )
                self.assertTrue(all("@图片1" in item["prompt"] for item in FakeArtClawClient.submissions))
                self.assertEqual([item["reference_count"] for item in submitted.json()["jobs"]], [1, 1, 1])
                import json

                saved_state = json.dumps(store.get(task_id).state, ensure_ascii=False)
                self.assertNotIn("cdn.example.com", saved_state)
            store.close()

    def test_artclaw_preview_rejects_out_of_range_shot_mapping(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("未安装 FastAPI TestClient 依赖")
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.db")
            agent = ShortDramaAgent(store=store)
            task_id = agent.create_task("生成三段短剧分镜").task_id
            agent.run(task_id)
            client = TestClient(create_fastapi_app(agent))
            response = client.post(
                f"/tasks/{task_id}/artclaw-preview",
                json={"shot_reference_urls": {"4": ["https://cdn.example.com/missing-shot.jpg"]}},
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("不存在的分镜编号", response.json()["detail"])
            store.close()

    def test_image_generation_plan_is_batched_persisted_and_idempotent(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("未安装 FastAPI TestClient 依赖")
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.db")
            agent = ShortDramaAgent(store=store, asset_store=LocalAssetStore(Path(directory) / "assets"))
            task_id = agent.create_task("生成角色和三个场景的参考图").task_id
            agent.run(task_id)
            FakeImageProviderClient.generate_count = 0
            with patch("integrations.image_provider.ImageProviderClient", FakeImageProviderClient):
                client = TestClient(create_fastapi_app(agent))
                preview = client.post(f"/tasks/{task_id}/image-preview", json={"max_new_images": 2})
                self.assertEqual(preview.status_code, 200)
                self.assertEqual(preview.json()["image_count"], 4)
                self.assertEqual(FakeImageProviderClient.generate_count, 0)

                blocked = client.post(f"/tasks/{task_id}/image-generate", json={"max_new_images": 2})
                self.assertEqual(blocked.status_code, 400)
                self.assertEqual(FakeImageProviderClient.generate_count, 0)

                first = client.post(
                    f"/tasks/{task_id}/image-generate",
                    json={"confirm_paid": True, "max_new_images": 2},
                )
                self.assertEqual(first.status_code, 200)
                self.assertEqual(first.json()["new_count"], 2)
                self.assertEqual(first.json()["remaining"], 2)

                second = client.post(
                    f"/tasks/{task_id}/image-generate",
                    json={"confirm_paid": True, "max_new_images": 2},
                )
                self.assertEqual(second.status_code, 200)
                self.assertEqual(second.json()["new_count"], 2)
                self.assertEqual(second.json()["remaining"], 0)

                third = client.post(
                    f"/tasks/{task_id}/image-generate",
                    json={"confirm_paid": True, "max_new_images": 2},
                )
                self.assertEqual(third.status_code, 200)
                self.assertEqual(third.json()["new_count"], 0)
                self.assertEqual(FakeImageProviderClient.generate_count, 4)

                assets = client.get(f"/tasks/{task_id}/image-assets")
                self.assertEqual(assets.status_code, 200)
                self.assertEqual(len(assets.json()["assets"]), 4)
                self.assertTrue(all(Path(item["local_file"]).exists() for item in assets.json()["assets"]))
                downloaded = client.get(f"/tasks/{task_id}/image-assets/character-1")
                self.assertEqual(downloaded.status_code, 200)
                self.assertTrue(downloaded.content.startswith(b"\x89PNG"))
                self.assertEqual(client.get(f"/tasks/{task_id}/image-assets/missing").status_code, 404)
                saved_state = store.get(task_id).state
                self.assertNotIn("b64_json", str(saved_state))
                self.assertNotIn("images.example.com", str(saved_state))
            store.close()

    def test_image_asset_download_rejects_path_outside_task_directory(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("未安装 FastAPI TestClient 依赖")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = TaskStore(root / "tasks.db")
            asset_store = LocalAssetStore(root / "assets")
            agent = ShortDramaAgent(store=store, asset_store=asset_store)
            task_id = agent.create_task("测试图片路径隔离").task_id
            record = store.get(task_id)
            outside = root / "outside.png"
            outside.write_bytes(b"\x89PNG\r\n\x1a\noutside")
            record.state["image_assets"] = [
                {"asset_key": "escape", "status": "saved", "local_file": str(outside)}
            ]
            store.save(record)
            client = TestClient(create_fastapi_app(agent))
            response = client.get(f"/tasks/{task_id}/image-assets/escape")
            self.assertEqual(response.status_code, 403)
            store.close()

    def test_task_list_and_cleanup_default_to_safe_preview(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("未安装 FastAPI TestClient 依赖")
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = TaskStore(root / "tasks.db")
            asset_store = LocalAssetStore(root / "assets")
            agent = ShortDramaAgent(store=store, asset_store=asset_store)
            task = agent.create_task("清理测试任务")
            old_record = store.get(task.task_id)
            old_record.status = "succeeded"
            old_record.updated_at = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
            old_record.state["image_assets"] = []
            store.save(old_record)
            (asset_store.root / task.task_id).mkdir(parents=True)
            (asset_store.root / "orphan").mkdir(parents=True)
            client = TestClient(create_fastapi_app(agent))
            listed = client.get("/tasks?limit=10")
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(listed.json()["tasks"][0]["task_id"], task.task_id)
            preview = client.post("/maintenance/cleanup", json={"older_than_days": 30})
            self.assertEqual(preview.status_code, 200)
            self.assertEqual(preview.json()["candidate_count"], 1)
            self.assertTrue(store.get(task.task_id))
            self.assertTrue((asset_store.root / task.task_id).exists())
            blocked = client.post("/maintenance/cleanup", json={"older_than_days": 30, "dry_run": False})
            self.assertEqual(blocked.status_code, 400)
            removed = client.post(
                "/maintenance/cleanup",
                json={"older_than_days": 30, "dry_run": False, "confirm_delete": True},
            )
            self.assertEqual(removed.status_code, 200)
            self.assertIsNone(store.get(task.task_id))
            self.assertFalse((asset_store.root / task.task_id).exists())
            self.assertTrue((asset_store.root / "orphan").exists())
            store.close()

    def test_image_generation_failure_keeps_main_task_and_resumes_remaining_assets(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("未安装 FastAPI TestClient 依赖")

        class FailSecondImageProviderClient(FakeImageProviderClient):
            generate_count = 0
            failed_once = False

            def generate_image(self, prompt, *, allow_paid):
                self.__class__.generate_count += 1
                if self.generate_count == 2 and not self.__class__.failed_once:
                    self.__class__.failed_once = True
                    raise RuntimeError("模拟图片服务暂时失败")
                return {"prompt": prompt, "sequence": self.generate_count, "allow_paid": allow_paid}

        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.db")
            agent = ShortDramaAgent(store=store, asset_store=LocalAssetStore(Path(directory) / "assets"))
            task_id = agent.create_task("生成可选角色和场景参考图").task_id
            agent.run(task_id)
            with patch("integrations.image_provider.ImageProviderClient", FailSecondImageProviderClient):
                client = TestClient(create_fastapi_app(agent))
                failed = client.post(
                    f"/tasks/{task_id}/image-generate",
                    json={"confirm_paid": True, "max_new_images": 4},
                )
                self.assertEqual(failed.status_code, 400)
                after_failure = store.get(task_id)
                self.assertEqual(after_failure.status, "succeeded")
                self.assertEqual(len(after_failure.state["image_assets"]), 1)

                resumed = client.post(
                    f"/tasks/{task_id}/image-generate",
                    json={"confirm_paid": True, "max_new_images": 4},
                )
                self.assertEqual(resumed.status_code, 200)
                self.assertEqual(resumed.json()["new_count"], 3)
                self.assertEqual(resumed.json()["remaining"], 0)
                self.assertEqual(len({item["asset_key"] for item in resumed.json()["assets"]}), 4)
                self.assertEqual(store.get(task_id).status, "succeeded")
            store.close()

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
