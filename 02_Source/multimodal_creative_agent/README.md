# MultimodalCreativeAgent（AI 多模态创作与短剧生成 Agent 平台）

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

当前可验证能力：阶段级检查点、有限重试、失败落库后恢复、结构化输出、一致性校验、线程池异步执行、任务事件查询和本地资产元数据归档。ArtClaw 已完成一次真实低成本视频生成和本地下载验收；Redis、Celery、WebSocket 已完成本地容器联调。AWS S3 按约定跳过，资产默认保存本地。

## 外部适配

已提供可选适配代码：`integrations/artclaw.py`、`integrations/image_provider.py`、`integrations/redis_backend.py`、`celery_worker.py` 和 FastAPI WebSocket 路由。ArtClaw 与图片生成的付费提交默认都被阻止，只有接口请求明确包含 `confirm_paid: true` 时才会发起可能计费的请求。

本地启动 Redis、API 和 Celery worker：

```powershell
docker compose -f 02_Source\docker-compose.yml up --build
```

启动后默认可访问 `http://localhost:8001/health` 和 `http://localhost:8001/ready`，网页控制台为 `http://localhost:8001/`，WebSocket 地址为 `ws://localhost:8001/ws/tasks/{task_id}`；如需其他端口可设置 `API_PORT`。不需要 Redis 时，直接运行 `demo.py` 仍使用 SQLite、线程池和本地资产目录。

ArtClaw 配置只从 `ARTCLAW_API_KEY_ACCOUNT_A`（兼容 `ARTCLAW_API_KEY`）环境变量读取，禁止写入代码、`.env`、日志或 Git。默认采用低成本测试参数：4 秒、480p、9:16、关闭音频；可用 `ARTCLAW_MODEL`、`ARTCLAW_RESOLUTION`、`ARTCLAW_ASPECT_RATIO`、`ARTCLAW_GENERATE_AUDIO` 覆盖。真实提交必须显式传入 `allow_paid=True`。

参考图必须是 ArtClaw 远程服务可以读取的公开 HTTPS 地址，单个分镜最多 9 张。本地文件路径、`localhost`、`.local` 域名和非公网 IP 地址会被拒绝。平台支持为每个分镜单独指定参考图；提交时会按图片顺序自动补充 `@图片1`、`@图片2` 等提示词，并增加角色外观、服装、场景和视觉风格连续性约束。参考图地址不会保存到 SQLite，只保存使用数量和来源类型，避免持久化可能带签名参数的地址。

图片资产生成是可选补充，不属于五阶段主流程。未配置图片服务时，短剧规划、分镜和 ArtClaw 功能仍正常运行。适配器面向兼容 `POST /images/generations` 的服务，支持响应中的 `data[0].b64_json` 或公网 HTTPS `data[0].url`，图片会保存到本地资产目录；密钥、Base64 原文和远程下载地址不会写入 SQLite。

需要启用时，在用户环境变量中配置以下项目，然后重新启动平台：

```powershell
[Environment]::SetEnvironmentVariable("IMAGE_API_BASE_URL", "https://你的服务地址/v1", "User")
[Environment]::SetEnvironmentVariable("IMAGE_API_KEY", "你的密钥", "User")
[Environment]::SetEnvironmentVariable("IMAGE_API_MODEL", "gpt-image-2", "User")
```

服务地址、鉴权方式和响应格式以实际供应商文档为准。云飞图片接口已完成正式使用接入；当前电脑没有可用密钥，因此本轮只做本机兼容链路复核，不重复调用云飞服务。

## 独立运行与真实规划

DeepSeek 是默认规划模型。平台优先读取用户环境变量 `DEEPSEEK_API_KEY`，将需求解析和分镜规划交给 DeepSeek；未设置时自动使用离线模型，平台仍可启动。若要临时强制离线模式，可设置 `MODEL_PROVIDER=offline`；正常使用不需要设置该变量。

```powershell
Set-Location E:\Agent\AIProjects\Project025_MultimodalCreativeAgent\02_Source
.\run_platform.ps1
```

脚本默认只监听本机 `127.0.0.1`，避免局域网其他设备调用付费接口。确实需要局域网访问时，才显式传入 `-HostAddress 0.0.0.0`，并自行增加认证和防火墙规则。

Docker 启动（脚本会主动读取当前用户环境变量，避免旧 PowerShell 会话漏传密钥）：

```powershell
.\run_docker.ps1 -Build
```

常用接口：

- `POST /tasks/async`：创建短剧规划任务。
- `GET /tasks/{task_id}`：查看规划状态和分镜结果。
- `POST /artclaw/videos`：由平台提交单个视频任务。
- `POST /tasks/{task_id}/artclaw-preview`：不产生费用，预览每个分镜将使用的参考图数量、来源和最终提示词。
- `POST /tasks/{task_id}/artclaw-submit`：把规划结果中的多个分镜批量提交到 ArtClaw。请求体必须包含 `confirm_paid: true`，已提交分镜会复用任务编号，避免重复扣费。
- `GET /tasks/{task_id}/artclaw-status`：统一查询该任务下所有分镜的 ArtClaw 状态。
- `POST /tasks/{task_id}/artclaw-download`：批量下载已完成分镜到本地资产目录，未完成项会返回 `pending`。
- `GET /artclaw/videos/{job_id}`：查询 ArtClaw 任务。
- `POST /artclaw/videos/{job_id}/download`：将已完成视频下载到本地资产目录，并返回稳定的 `download_url`；`local_file` 是运行环境内部路径。
- `POST /tasks/{task_id}/image-preview`：免费预览角色和场景图片任务，不调用图片服务。
- `POST /tasks/{task_id}/image-generate`：按批次生成可选图片资产；必须包含 `confirm_paid: true`，已成功项不会重复生成。
- `GET /tasks/{task_id}/image-assets`：查看已保存的本地图片资产元数据。
- `GET /tasks/{task_id}/image-assets/{asset_key}`：读取当前任务目录中的单张已保存图片；接口会拒绝目录外路径。
- `GET /`：打开本地创作工作台，可创建任务、查看状态、查看图片和预览清理结果。
- `GET /tasks`：按更新时间查看任务列表。
- `POST /maintenance/cleanup`：预览或确认清理过期任务及其资产目录。
- `GET /usage-audit`：查看外部付费调用的最小审计记录（不含密钥和完整提示词）。
- `GET /metrics`：输出基础 Prometheus 指标，供服务器监控采集。

`GET /health` 会返回 `model_provider`（`deepseek` 或 `offline`）、`model_name`、`artclaw_configured` 和 `image_provider_configured`，可用于确认独立运行时实际采用的模型和外部服务配置，不会返回密钥。`GET /ready` 会检查 SQLite 和已配置的 Redis 是否可用，适合 Docker、反向代理或云平台健康探测；它不会主动调用 DeepSeek、ArtClaw 或图片生成服务。

当前代码已达到上线候选状态；正式上线只差目标服务器、持久化磁盘、Redis、HTTPS/域名和密钥管理的环境适配。具体步骤见 `05_Docs/上线适配清单.md`。
配置 Redis 后，ArtClaw 和图片生成的付费提交使用跨进程锁；无 Redis 时回退单进程线程锁。对象存储暂缓，资产默认保存到 `/data`。
Docker Compose 支持通过 `MODEL_PROVIDER=offline` 强制离线模型，适合没有 DeepSeek 密钥时验证独立运行；默认值为 `deepseek`。

逐分镜参考图预览示例：

```json
{
  "reference_urls": ["https://cdn.example.com/default-room.jpg"],
  "shot_reference_urls": {
    "1": ["https://cdn.example.com/hero-front.jpg"],
    "3": ["https://cdn.example.com/hero-ending.jpg"]
  },
  "duration_seconds": 4,
  "max_new_jobs": 3
}
```

`reference_urls` 是未单独配置分镜时的默认参考图；`shot_reference_urls` 使用从 1 开始的分镜编号覆盖默认值。先把请求体发送到预览接口，确认结果后再增加 `"confirm_paid": true`，发送到批量提交接口。
