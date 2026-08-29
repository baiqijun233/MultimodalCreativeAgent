# 多模态创作与短剧生成 Agent 平台

这是一个可独立运行的多模态创作任务平台，支持需求分析、分镜规划、结构化校验、异步执行、任务持久化和可选的视频/图片服务接入。

## 已验证能力

- DeepSeek 真实规划与严格结构化校验
- ArtClaw 真实低成本视频生成、轮询和下载
- 可选图片生成接口，支持分批、幂等和失败续跑
- FastAPI 网页控制台、任务列表、事件查询和安全清理
- SQLite 持久化、Redis、Celery、WebSocket
- Redis 跨进程付费锁、额度审计和 `/metrics` 指标
- Docker 独立运行与重启后数据持久化

## 快速启动

### Docker

```powershell
docker compose -f 02_Source\docker-compose.yml up -d --build
```

启动后访问：

- 网页控制台：http://127.0.0.1:8001/
- 健康检查：http://127.0.0.1:8001/health
- 就绪检查：http://127.0.0.1:8001/ready

没有 DeepSeek 密钥时，可使用离线模式：

```powershell
$env:MODEL_PROVIDER = "offline"
docker compose -f 02_Source\docker-compose.yml up -d
```

### 测试

```powershell
python -m unittest discover -s 06_Tests -v
```

## 目录说明

- `02_Source`：源码、Docker 编排和启动脚本
- `05_Docs`：技术说明与上线适配清单
- `06_Tests`：自动化测试
- `07_Logs`：验收日志和回退备份
- `08_Deliverables`：已验收的视频交付物

正式部署前需要配置目标服务器、持久化磁盘、密钥、域名、HTTPS 和公网鉴权。对象存储、自动剪辑和告警增强属于后续升级计划。
