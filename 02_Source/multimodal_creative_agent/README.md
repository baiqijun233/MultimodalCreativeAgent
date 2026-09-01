# MultimodalCreativeAgent 源码

这里是短视频创作任务的状态机、存储、异步执行和外部服务适配器。任务依次经过需求解析、规划、校验、资产处理和结果汇总，阶段状态会写入 SQLite，失败任务可以从已完成阶段继续。

## 本地运行

```powershell
Set-Location 02_Source
python -m unittest discover -s ..\06_Tests -v
python .\multimodal_creative_agent\demo.py
```

容器方式：

```powershell
docker compose -f .\docker-compose.yml up -d --build
```

## 模块

- `short_drama_agent.py`：任务模型、阶段编排、校验和接口路由。
- `async_runner.py`、`celery_worker.py`：线程池和 Celery 执行入口。
- `common/`：资产路径、事件和 SQLite 存储。
- `integrations/`：模型、视频、图片、Redis 和分布式锁适配器。
- `dashboard.py`：本地创作控制台。

## 配置与费用控制

密钥只通过环境变量注入，例如 `DEEPSEEK_API_KEY`、`ARTCLAW_API_KEY_ACCOUNT_A` 和 `IMAGE_API_KEY`。未配置外部模型时使用离线规划。视频和图片提交接口默认拒绝可能计费的请求，必须显式传入 `confirm_paid: true`（底层客户端使用 `allow_paid=True`）。

参考图只接受供应商可访问的 HTTPS 地址；本地路径、内网地址和签名内容不会写入任务数据库。资产下载接口会限制在当前任务目录内。

## 验证

```powershell
Set-Location ..
python -m unittest discover -s 06_Tests -v
python -m compileall -q 02_Source 06_Tests
docker compose -f 02_Source\docker-compose.yml config
```
