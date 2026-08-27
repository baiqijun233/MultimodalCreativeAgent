# AI 多模态创作与短剧生成 Agent 平台

本项目展示多模态创作任务的状态机编排、结构化输出、异步任务边界、失败重试和 SQLite 状态持久化。核心逻辑默认只依赖 Python 标准库，可替换接入 VLM/LLM、对象存储和消息队列。

`short_drama_agent.py` 提供可选 `create_fastapi_app` 适配器，安装 `fastapi` 与 `pydantic` 后可接入 HTTP 服务。当前本地代码不宣称已接入 AWS S3、Redis、Celery 或 WebSocket 生产环境。

运行测试：

```powershell
python -m unittest discover -s 06_Tests -v
```

运行本地完整演示：

```powershell
python 02_Source\multimodal_creative_agent\demo.py
```

演示会在 `.local_demo` 下保存 SQLite 任务状态和资产元数据，完整经过需求解析、规划、一致性校验、资产任务和结果汇总五个阶段。

当前可验证能力：阶段级检查点、有限重试、失败落库后恢复、结构化输出、一致性校验、线程池异步执行、任务事件查询和本地资产元数据归档。真实图片/视频/音频生成仍需接入具体模型服务；AWS S3、Redis、Celery、WebSocket 属于后续生产适配接口。

## 外部适配

已提供可选适配代码：`integrations/artclaw.py`、`integrations/redis_backend.py`、`celery_worker.py` 和 FastAPI WebSocket 路由。ArtClaw 客户端支持账户查询、视频任务提交和任务查询；提交默认被阻止，只有显式 `allow_paid=True` 才会发起可能计费的请求。

本地启动 Redis、API 和 Celery worker：

```powershell
docker compose -f 02_Source\docker-compose.yml up --build
```

启动后默认可访问 `http://localhost:8001/health`，WebSocket 地址为 `ws://localhost:8001/ws/tasks/{task_id}`；如需其他端口可设置 `API_PORT`。不需要 Redis 时，直接运行 `demo.py` 仍使用 SQLite、线程池和本地资产目录。

ArtClaw 配置只从 `ARTCLAW_API_KEY_ACCOUNT_A`（兼容 `ARTCLAW_API_KEY`）环境变量读取，禁止写入代码、`.env`、日志或 Git。默认采用低成本测试参数：4 秒、480p、9:16、关闭音频；可用 `ARTCLAW_MODEL`、`ARTCLAW_RESOLUTION`、`ARTCLAW_ASPECT_RATIO`、`ARTCLAW_GENERATE_AUDIO` 覆盖。真实提交必须显式传入 `allow_paid=True`。
