<div align="center">

# MultimodalCreativeAgent

### 多模态创作任务编排与短视频生产服务

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](02_Source/requirements-optional.txt)
[![CI](https://github.com/baiqijun233/MultimodalCreativeAgent/actions/workflows/tests.yml/badge.svg)](https://github.com/baiqijun233/MultimodalCreativeAgent/actions/workflows/tests.yml)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](02_Source/docker-compose.yml)
[![Tests](https://img.shields.io/badge/tests-unittest-2ea44f)](06_Tests)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**需求输入 → 结构化分镜 → 异步执行 → 可追踪资产**

</div>

MultimodalCreativeAgent 面向短剧、广告和内容团队的创作任务管理。系统把自然语言需求拆成角色、场景和分镜计划，经过结构化校验后进入异步任务队列，并保留阶段状态、失败重试和资产元数据。

## 项目预览

![桌面控制台](03_Assets/screenshots/dashboard-desktop.png)
![移动端控制台](03_Assets/screenshots/dashboard-mobile.png)

截图来自本地运行的控制台，展示任务创建、状态查看和资产预览流程。

## 核心能力

- 需求解析、角色/场景/分镜规划和结构化一致性校验。
- SQLite 任务状态、阶段检查点、有限重试和失败恢复。
- FastAPI 控制台、任务事件、WebSocket 和 Prometheus 指标。
- Celery + Redis 异步执行，可选接入视频和图片服务。
- 付费调用默认需要显式确认，跨进程锁避免重复提交。
- 资产目录隔离，下载接口不暴露运行环境内部路径。

## 运行架构

```text
需求 → FastAPI/控制台 → 规划与校验 → Celery Worker
                                  ├→ Redis（队列/状态/锁）
                                  └→ SQLite + /data（任务/资产）
                                             ↓
                                  视频或图片供应商适配器
```

## 快速开始

环境要求：Python 3.11+；容器运行需要 Docker Desktop 或 Docker Engine。

```powershell
docker compose -f 02_Source\docker-compose.yml up -d --build
```

访问控制台 <http://127.0.0.1:8001/>，健康检查为 <http://127.0.0.1:8001/health>，就绪检查为 <http://127.0.0.1:8001/ready>。

没有外部模型密钥时，使用离线模式验证完整任务链路：

```powershell
$env:MODEL_PROVIDER = "offline"
docker compose -f 02_Source\docker-compose.yml up -d
```

本机 Python 方式：

```powershell
Set-Location 02_Source
.\run_platform.ps1
```

## 配置与接口

密钥只通过环境变量注入，不写入代码、日志或 Git。常用变量包括 `MODEL_PROVIDER`、`DEEPSEEK_API_KEY`、`ARTCLAW_API_KEY`、`TASK_DATABASE_PATH` 和 `ASSET_ROOT`。所有可能产生费用的接口都要求请求体显式包含 `confirm_paid: true`。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/tasks/async` | 创建异步创作任务 |
| GET | `/tasks/{task_id}` | 查看状态和分镜结果 |
| GET | `/tasks/{task_id}/events` | 查询阶段事件 |
| POST | `/tasks/{task_id}/artclaw-preview` | 预览付费提交内容 |
| POST | `/tasks/{task_id}/artclaw-submit` | 显式确认后提交视频任务 |
| POST | `/tasks/{task_id}/image-preview` | 预览图片资产计划 |
| GET | `/metrics` | 输出基础指标 |

## 测试与验证

```powershell
python -m unittest discover -s 06_Tests -v
python -m compileall -q 02_Source 06_Tests
docker compose -f 02_Source\docker-compose.yml config
```

## 项目结构

```text
02_Source/
├─ multimodal_creative_agent/  任务编排、存储和外部适配器
├─ run_platform.ps1            本机启动脚本
├─ run_docker.ps1              容器启动脚本
├─ Dockerfile                  容器构建文件
└─ docker-compose.yml          API、Worker 和 Redis
```

## 实现范围与第三方组件

维护者主导任务模型、状态机、接口、安全边界、测试和部署配置。DeepSeek、视频/图片供应商、Redis、Celery 和 FastAPI 作为可替换依赖，生产环境需按供应商协议配置凭证和网络访问。

## 当前边界与路线图

当前版本支持本机和单机容器验证，资产默认写入本地持久化目录；正式部署还需要服务器磁盘、对象存储、HTTPS、访问控制、监控告警和成本预算。后续将继续完善多人权限、对象存储、媒体合成和更细粒度的配额策略。

## 贡献、许可证与安全

欢迎通过 Issue 或 Pull Request 参与。提交前请运行测试并移除密钥、运行数据和本机路径。本项目使用 [MIT License](LICENSE)，安全问题请按 [SECURITY.md](SECURITY.md) 联系维护者。
