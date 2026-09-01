<div align="center">

# MultimodalCreativeAgent

### 多模态创作任务编排与短视频生产服务

**需求输入 → 结构化分镜 → 异步执行 → 可追踪资产 → 成本可控交付**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](02_Source/requirements-optional.txt)
[![CI](https://github.com/baiqijun233/MultimodalCreativeAgent/actions/workflows/tests.yml/badge.svg)](https://github.com/baiqijun233/MultimodalCreativeAgent/actions/workflows/tests.yml)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](02_Source/docker-compose.yml)
[![Tests](https://img.shields.io/badge/tests-35%20passed-2ea44f)](06_Tests)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

<p>
  <a href="#project-preview">项目预览</a> ·
  <a href="#features">核心能力</a> ·
  <a href="#architecture">运行架构</a> ·
  <a href="#quick-start">快速开始</a> ·
  <a href="#verification">测试验证</a> ·
  <a href="#roadmap">路线图</a>
</p>

</div>

MultimodalCreativeAgent 面向短剧、广告和内容团队的创作任务管理。系统将自然语言需求拆成角色、场景和分镜计划，经过结构化校验后进入异步任务队列，并保留阶段状态、失败重试和资产元数据。

> **当前版本 · v0.1.0**：35 项自动化测试通过；网页控制台、异步 Worker、失败恢复、付费调用保护和持久化链路均已完成本机验证。外部生成服务按需配置，离线模式可以独立验证任务流程。

<a id="project-preview"></a>

## 🖼️ 项目预览

<table>
  <tr>
    <td width="50%"><strong>桌面控制台</strong><br><img src="03_Assets/screenshots/dashboard-desktop.png" alt="桌面创作控制台"></td>
    <td width="50%"><strong>移动端控制台</strong><br><img src="03_Assets/screenshots/dashboard-mobile.png" alt="移动端创作控制台"></td>
  </tr>
</table>

截图来自本地运行的控制台，展示任务创建、状态查看和资产预览流程。

<a id="features"></a>

## ✨ 核心能力

| 模块 | 能力 |
| --- | --- |
| 创作规划 | 需求解析、角色/场景/分镜生成和结构化一致性校验 |
| 任务执行 | SQLite 状态、阶段检查点、有限重试、失败恢复和事件查询 |
| 异步处理 | Celery + Redis Worker，支持任务状态、跨进程锁和 WebSocket 事件 |
| 外部适配 | DeepSeek 规划、视频供应商、图片生成服务和可选对象存储接口 |
| 成本与安全 | 付费调用显式确认、额度审计、资产目录隔离和下载路径校验 |
| 运维入口 | FastAPI 控制台、健康/就绪检查、Prometheus 指标和 Docker Compose |

### 关键设计取舍

- **先把创作要求变成结构化计划**：角色、场景和分镜通过校验后才进入生成阶段，减少格式漂移带来的返工。
- **任务状态和媒体资产分开管理**：SQLite 保存阶段与元数据，资产写入受控目录，失败后可以从已完成阶段继续。
- **付费动作必须再次确认**：预览和正式提交使用不同接口，并配合额度记录与跨进程锁，降低重复调用风险。

<a id="architecture"></a>

## 🧩 运行架构

```mermaid
flowchart TB
    A["需求输入"] --> B["FastAPI / 网页控制台"]
    B --> C["分析与分镜规划"]
    C --> D["结构化校验"]
    D --> E["Celery Worker"]
    E --> F["Redis<br/>队列、状态与锁"]
    E --> G["SQLite 与数据目录<br/>任务与资产"]
    E --> H["视频或图片服务"]
```

<a id="quick-start"></a>

## ⚡ 快速开始

环境要求：Python 3.11+；容器运行需要 Docker Desktop 或 Docker Engine。

```powershell
docker compose -f 02_Source\docker-compose.yml up -d --build
```

访问控制台 <http://127.0.0.1:8001/>，健康检查为 <http://127.0.0.1:8001/health>，就绪检查为 <http://127.0.0.1:8001/ready>，指标接口为 <http://127.0.0.1:8001/metrics>。

没有外部模型密钥时可以使用离线模式：

```powershell
$env:MODEL_PROVIDER = "offline"
docker compose -f 02_Source\docker-compose.yml up -d
```

本机 Python 方式：

```powershell
Set-Location 02_Source
.\run_platform.ps1
```

## 📦 已发布版本

- Release：[MultimodalCreativeAgent v0.1.0](https://github.com/baiqijun233/MultimodalCreativeAgent/releases/tag/v0.1.0)
- Container：`ghcr.io/baiqijun233/multimodalcreativeagent`

```powershell
docker pull ghcr.io/baiqijun233/multimodalcreativeagent:0.1.0
docker pull ghcr.io/baiqijun233/multimodalcreativeagent:latest
```

两个标签的公开镜像清单已验证可读取；版本标签适合固定部署，`latest` 用于跟随已发布更新。

## 🔐 配置与接口

密钥只通过环境变量注入，例如 `DEEPSEEK_API_KEY`、`ARTCLAW_API_KEY_ACCOUNT_A` 和 `IMAGE_API_KEY`。未配置外部模型时使用离线规划。所有可能产生费用的提交接口都要求显式确认。

| 配置项 | 作用 | 默认行为 |
| --- | --- | --- |
| `MODEL_PROVIDER` | 选择规划服务 | 未配置外部能力时可使用 `offline` |
| `TASK_DATABASE_PATH` | SQLite 任务数据库位置 | Docker 中使用持久化数据目录 |
| `ASSET_ROOT` | 生成资产根目录 | 仅允许在受控目录内读写 |
| `ARTCLAW_RESOLUTION` | 视频分辨率 | 使用项目的低成本默认值 |
| `ARTCLAW_GENERATE_AUDIO` | 是否生成音频 | 默认关闭 |

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/tasks/async` | 创建异步创作任务 |
| GET | `/tasks/{task_id}` | 查看状态和分镜结果 |
| GET | `/tasks/{task_id}/events` | 查询阶段事件 |
| POST | `/tasks/{task_id}/artclaw-preview` | 预览视频提交内容 |
| POST | `/tasks/{task_id}/artclaw-submit` | 确认后提交视频任务 |
| POST | `/tasks/{task_id}/image-preview` | 预览图片资产计划 |
| POST | `/tasks/{task_id}/image-generate` | 确认后生成图片资产 |
| POST | `/tasks/{task_id}/artclaw-download` | 下载已完成视频 |
| GET | `/usage-audit` | 查看最小额度审计记录 |
| GET | `/metrics` | 输出基础指标 |

<a id="verification"></a>

## ✅ 测试与验证

```powershell
python -m unittest discover -s 06_Tests -v
python -m compileall -q 02_Source 06_Tests
docker compose -f 02_Source\docker-compose.yml config
```

| 检查项 | 当前结果 |
| --- | --- |
| 自动化测试 | 35 项通过，覆盖状态机、重试恢复、付费保护、资产路径、异步任务和接口注册 |
| Python 编译 | `02_Source` 与 `06_Tests` 通过 |
| Compose 配置 | API、Worker 与 Redis 编排解析通过 |
| 运行链路 | 控制台、健康/就绪探针、异步任务、事件查询与重启恢复已验证 |

外部服务会受到账号权限、额度和网络环境影响；仓库中的验证结果只描述已执行的功能链路，不表示固定生成质量或成功率。

## 📁 项目结构

```text
02_Source/
├─ multimodal_creative_agent/  任务编排、存储和外部适配器
├─ run_platform.ps1            本机启动脚本
├─ run_docker.ps1              容器启动脚本
├─ Dockerfile                  容器构建文件
└─ docker-compose.yml          API、Worker 和 Redis
```

## 🧱 实现范围与第三方组件

维护者主导任务模型、状态机、接口、安全边界、测试和部署配置。DeepSeek、视频/图片供应商、Redis、Celery 和 FastAPI 作为可替换依赖，生产环境需按供应商协议配置凭证和网络访问。

<a id="roadmap"></a>

## 🗺️ 当前边界与路线图

当前版本支持本机和单机容器验证，资产默认写入本地持久化目录。正式部署还需要服务器磁盘、对象存储、HTTPS、访问控制、监控告警和成本预算；后续将完善多人权限、媒体合成和更细粒度的配额策略。

## 🤝 贡献、许可证与安全

欢迎通过 Issue 或 Pull Request 参与。提交前请运行测试并移除密钥、运行数据和本机路径。本项目使用 [MIT License](LICENSE)，安全问题请按 [SECURITY.md](SECURITY.md) 联系维护者。
