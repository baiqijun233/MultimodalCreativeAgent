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
