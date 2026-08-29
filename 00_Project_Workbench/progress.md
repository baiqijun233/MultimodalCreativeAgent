# 项目进度

## 2026-08-26

- 从组合工程拆出独立项目目录。
- 完成多模态 Agent 离线状态机、SQLite 持久化、重试和可选 FastAPI 适配器。
- 已添加 2 项标准库自动化测试，待运行验证。

## 2026-08-26 - 骨架交接

- 已完成基础目录、状态机 Agent、SQLite 持久化、重试和 2 项标准库测试，测试结果由简历任务复核为全部通过。
- 后续完整实现与生产适配由其他对话负责；简历仅使用当前可验证的工程能力。

## 2026-08-27 - 多模态创作链路补全

- 新增 `validate` 一致性校验阶段，覆盖角色、场景、分镜和素材类型约束。
- 新增本地资产元数据归档、内存事件总线、线程池异步执行器和 `demo.py` 演示入口。
- 增强失败状态落库、重试记录和从失败阶段恢复能力；测试由 2 项扩展到 6 项。
- 新增项目技术说明 `05_Docs/ai_multimodal_agent_project.md`，明确本地实现与 AWS S3/Redis/Celery/WebSocket 生产适配边界。
- 下一步：如需改成“已接入”表述，必须提供对应服务配置并完成真实服务端到端验证。
- 验证命令：`python -m unittest discover -s 06_Tests -v`、`python -m compileall -q 02_Source`，以及 `python 02_Source\multimodal_creative_agent\demo.py --workdir 04_Data\local_demo_check_20260827`，均成功。
- Git：已初始化本地仓库，首个提交为 `53a9b2d`；本次索引和进度同步后继续保留本地提交，不推送远程。

## 2026-08-27 - 外部服务适配

- 新增 ArtClaw HTTP 客户端，支持账户查询、视频任务提交、任务查询和计费提交保护。
- 新增 Redis 状态缓存/事件总线、Celery worker、FastAPI WebSocket 推送与统一运行时配置。
- 新增 Dockerfile、Docker Compose 本地 Redis/API/worker 编排和可选依赖清单。
- 测试扩展至 10 项并全部通过；ArtClaw 计费接口未执行，避免未经确认产生外部费用。
- Docker 已安装并验证：镜像构建成功，Redis 健康，Celery worker 注册并消费 `creative.run_task`，API 因本机 8000 被占用改用 `8001`。
- 容器端到端任务成功：五阶段完成、Redis 事件 11 条、资产数 3；WebSocket 客户端收到阶段事件和最终快照。
- ArtClaw 仍只读取环境变量，未执行真实计费提交；AWS S3 按约定跳过，本地资产存储保持为默认实现。

## 2026-08-27 - 低成本测试参数

- ArtClaw 客户端新增可配置模型、画幅、分辨率和音频开关。
- 默认真实提交参数调整为 4 秒、480p、9:16、关闭音频，用于最低成本验证；仍需显式 `allow_paid=True` 才会提交。
- 新增低成本默认值自动化测试，项目测试共 11 项全部通过。
- 当前 PowerShell 会话未检测到 `ARTCLAW_API_KEY_ACCOUNT_A` 或 `ARTCLAW_API_KEY`，因此未查询账户、未提交任务、未产生费用。

## 2026-08-27 - ArtClaw 真实低成本生成验收

- 从用户指定的本机密钥文件读取密钥，仅注入当前命令进程，未写入代码、日志或 Git。
- 账户查询成功：可用积分 116，锁定积分 0。
- 使用 4 秒、480p、9:16、关闭音频、无参考图提交一次真实视频任务，任务编号 `91d0be35-d728-4cea-95f4-e4745a415383`，服务端状态 `success`。
- 视频已下载到 `08_Deliverables/artclaw_low_cost_test_91d0be35.mp4`；本地检查为 MP4/H.264、496x864、24fps、4.04 秒、无音频流，首帧视觉检查通过。
- 任务详情和下载记录保存于 `07_Logs/artclaw_job_91d0be35.json`；首帧检查图保存于 `07_Logs/artclaw_low_cost_test_frame.png`。

## 2026-08-28 - 阶段收尾复核

- 复核 ArtClaw 任务日志、视频文件、媒体探针结果和首帧检查图，均可读取且相互一致。
- 全文扫描未发现 API 密钥、密钥赋值或请求头中的敏感值残留；密钥文件仍在项目外，仅作为本机运行输入。
- 当前项目可对外说明为：已完成 ArtClaw 测试账号的一次真实低成本生成验收；AWS S3 仍跳过，资产本地保存。

## 2026-08-28 - 平台独立运行与闭环接入

- DeepSeek 可选适配已加入运行时：配置 `DEEPSEEK_API_KEY` 后自动用于需求解析和分镜规划；缺少密钥时自动回退离线模型，平台仍可启动。
- ArtClaw 已接入平台 API：单镜头提交、任务查询、单镜头下载，以及按规划分镜批量提交、统一状态查询和批量下载。
- 分镜任务编号持久化到 SQLite，重复批量提交会复用已有任务，避免重复计费。
- DeepSeek 和 ArtClaw 密钥已写入当前用户环境变量，均未写入项目、日志或 Git；Docker Compose 已转发对应环境变量。
- 新增独立启动脚本 `02_Source/run_platform.ps1`，重启后可自行启动平台，不依赖当前对话。
- 自动化测试 12 项通过，Docker Compose 配置检查和 API 镜像构建通过。

## 2026-08-28 - 独立运行复核

- DeepSeek 和 ArtClaw 密钥均已写入当前用户环境变量，项目代码不保存密钥。
- 有 `DEEPSEEK_API_KEY` 时运行时选择 `DeepSeekModel`；无该变量时选择 `DeterministicModel`，两种模式均可启动。
- 新增 `/tasks/{task_id}/artclaw-status` 和 `/tasks/{task_id}/artclaw-download`，完成分镜批量状态查询与批量下载闭环。
- 12 项自动化测试、Python 编译检查、路由检查、Docker Compose 配置检查和 API/Worker 镜像构建全部通过。
- 本轮未再次调用真实计费接口；已生成的 ArtClaw 测试视频和任务记录继续保留。
- DeepSeek `/models` 鉴权检查成功；根据当前账号可用模型列表，将默认模型从 `deepseek-chat` 调整为 `deepseek-v4-flash`，避免独立运行时调用不存在的模型。

## 2026-08-28 - 优先模型与缺口修复

- 运行时默认优先 DeepSeek，可用 `MODEL_PROVIDER=offline` 显式切换离线模式；`GET /health` 返回当前模型提供方和 ArtClaw 是否配置，不暴露密钥。
- 修复 ArtClaw 分镜批量提交的部分成功持久化问题：中途失败时已提交任务编号立即落库，后续重试会复用编号，避免重复计费。
- 完成自查：核心代码无 TODO/FIXME；剩余外部条件为 DeepSeek/ArtClaw 服务配额、Redis/Celery 运行环境和 AWS S3（按约定跳过）。
- 修复独立启动脚本在旧 PowerShell 会话中漏读用户级密钥的问题，新增 Docker 启动脚本；DeepSeek 结构化结果增加字段类型和空结果校验。
- 真实 DeepSeek 最小链路验证成功：生成 2 个角色、3 个场景和 3 个自包含分镜提示词，最终状态 `ready`；本次未调用 ArtClaw。
- ArtClaw 批量接口拆分独立请求对象，默认每次最多新增 3 个付费任务，并通过接口测试确认分批提交和任务编号复用。
- 本地启动脚本、Docker API 端口和 Redis 端口默认只绑定 `127.0.0.1`，降低未授权调用付费接口的风险。
- 当前仍未包含网页界面、用户登录/权限系统、跨进程分布式提交锁、自动剪辑合成和生产部署监控；这些不影响单机 API 演示，但属于产品化阶段缺口。

## 2026-08-29 - 共享对话续做与独立复核

- 从共享对话恢复现场，先将上一轮已通过 15 项测试的未提交改动保存为本地 Git 检查点 `c3d1847`，未推送远程。
- 新增 DeepSeek 默认优先选择测试，确认配置密钥且未显式指定离线模式时使用 `DeepSeekModel`。
- 复现并修复结构化校验缺口：现在会拒绝场景数与分镜数不一致、不支持的素材类型、空角色/场景/素材和缺少 `scene`、`shot`、`prompt` 的分镜。
- 自动化测试由 15 项扩展到 19 项，全部通过；Python 编译、PowerShell 启动脚本语法和 Docker Compose 配置检查通过。
- 当前容器健康检查返回 `model_provider=deepseek`、`model_name=deepseek-v4-flash`，Redis 健康，API 和 Worker 均在运行；未调用 DeepSeek 生成接口，也未提交 ArtClaw 付费任务。
- Docker 重建两次均在拉取 Docker Hub `python:3.11-slim` 元数据时遇到 EOF，未进入项目代码构建阶段；现有容器未受影响。后续网络恢复后需再次执行 `docker compose build --pull=false` 或 `run_docker.ps1 -Build`。
- 补充本地运行目录和 Redis 备份目录的 Git 忽略规则，文件继续保留在 `04_Data`，没有删除。
- 产品化缺口已写入技术文档：分镜参考图映射、真实生图/配音/字幕、自动剪辑成片、网页界面、登录权限、分布式幂等和生产监控。

## 2026-08-29 - 逐分镜参考图映射

- 新增 `POST /tasks/{task_id}/artclaw-preview`，可在不调用 ArtClaw、不产生费用的情况下预览每个分镜的参考图来源、数量和最终提示词。
- 批量提交支持 `shot_reference_urls`：每个分镜可独立使用最多 9 个公开 HTTPS 参考图；未单独配置时使用 `reference_urls` 默认列表。
- 最终提示词会按实际图片顺序自动加入 `@图片1`、`@图片2` 等引用，并补充角色脸型、发型、服装、场景布局和视觉风格连续性要求。
- 拒绝本地路径、localhost、`.local` 和非公网 IP 地址，因为 ArtClaw 远程服务无法读取这些资源；本地文件自动上传仍需等待可核实的官方上传 API。
- 参考图 URL 不写入 SQLite，仅在请求期间使用；任务状态只记录参考图数量和来源，避免保存带签名参数的地址。
- 新增 3 类测试：本地路径拒绝、逐分镜映射与默认兜底、越界分镜编号拒绝。项目自动化测试由 19 项扩展到 22 项并全部通过。
- 最新源码临时启动离线 API 后，真实 HTTP 链路验证成功：创建并运行 3 分镜任务，预览来源依次为 `shot/default/shot`，每个分镜 1 张参考图；未执行任何付费提交。
- Docker Hub 网络恢复后，最新 API/Worker 镜像已构建并重新创建容器；`8001` 健康检查显示 DeepSeek 与 ArtClaw 已配置，OpenAPI 已包含预览和提交路由，Celery Worker `ping` 返回 `pong`。

## 2026-08-29 - 可选图片资产接口

- 按用户确认的产品边界，将角色和场景图片生成实现为独立可选接口，不加入五阶段主状态机；未配置图片服务时，规划、分镜、ArtClaw、API 和 Worker 均可正常运行。
- 新增兼容 `POST /images/generations` 的图片服务适配器，支持 `data[0].b64_json` 和公网 HTTPS `data[0].url`，默认模型 `gpt-image-2`、默认尺寸 `1024x1024`。
- 新增 `image-preview`、`image-generate` 和 `image-assets` 三条任务接口；生成必须显式提交 `confirm_paid: true`，支持分批处理、成功即落盘和落库、重复调用跳过已完成项、中途失败后继续补剩余项。
- 图片仅保存到任务的本地 `reference_images` 目录；密钥、Base64 原文和远程结果 URL 不写入 SQLite。下载限制为公网 HTTPS，文件限制为 25 MB，并校验 PNG、JPEG 或 WebP 文件签名。
- 自动化测试由 22 项扩展到 25 项并全部通过，覆盖兼容请求格式、付费保护、Base64 落盘、路由注册、分批幂等和失败续跑；Python 编译、PowerShell 语法、Compose 配置和差异格式检查均通过。
- 用本机临时 HTTP 兼容服务完成真实网络链路验证：平台成功请求 `/v1/images/generations`、接收 Base64 图片并落盘，主任务状态保持 `succeeded`；临时服务与文件已清理，未产生外部费用。
- 最终 API/Worker 镜像已重建，3 个容器均运行；`GET /health` 返回正常且 `image_provider_configured=false`，OpenAPI 包含 3 条图片路由，未确认付费的生成请求返回 HTTP 400，Celery Worker 返回 `pong`。
- 新增和修改文件敏感值扫描为 0，项目中没有 `.env` 文件。本轮没有调用 DeepSeek、图片服务或 ArtClaw 的真实计费生成接口。
- 云飞图片接口已完成正式使用接入；当前电脑没有可用密钥，本轮无法重复真实调用，保留此前已完成的正式使用结论。

## 2026-08-29 - 图片资产读取闭环

- 新增 `GET /tasks/{task_id}/image-assets/{asset_key}`，外部调用方可以直接读取已保存的单张图片，不需要接触服务器本地路径。
- 下载接口仅允许当前任务的 `reference_images` 目录，校验任务归属、文件存在性和路径边界；目录外路径返回 HTTP 403，不存在资产返回 HTTP 404。
- 自动化测试由 25 项扩展到 26 项并全部通过，包含正常图片读取、缺失资产和目录穿越拒绝。
- Docker 最终重建后首次健康探测遇到容器重启竞态返回 502；查看日志确认 Uvicorn 已正常启动，等待 2 秒后健康检查恢复 `ok`，图片下载路由存在，Celery Worker 返回 `pong`。

## 2026-08-29 - 控制台与安全清理

- 新增轻量网页控制台 `GET /`：支持创建并运行短剧任务、刷新任务列表、查看图片资产和执行清理预览；不引入前端构建依赖。
- 新增 `GET /tasks` 任务列表接口，返回状态、需求摘要、更新时间、图片资产数和 ArtClaw 任务数。
- 新增 `POST /maintenance/cleanup`：默认只预览超过指定天数的旧任务；实际删除必须同时设置 `dry_run=false` 与 `confirm_delete=true`，并只删除对应任务目录，不触碰孤立资产目录。
- 自动化测试由 26 项扩展到 27 项并全部通过，覆盖任务列表、清理预览、删除确认和孤立目录保留。
- 云飞图片接口按用户确认记录为已完成正式使用；当前电脑没有密钥，本轮未重复调用外部服务。
- 鉴权、多实例分布式锁、额度审计、生产监控、自动剪辑合成列入未来升级计划，本轮不实施。
