# 贡献指南

感谢关注 MultimodalCreativeAgent。提交 Issue 或 Pull Request 前，请先确认问题可以在本地复现，并避免提交密钥、运行数据和生成缓存。

## 提交前检查

```powershell
python -m unittest discover -s 06_Tests -v
python -m compileall -q 02_Source
docker compose -f 02_Source\docker-compose.yml config --quiet
```

## 提交规范

- 一个提交尽量只解决一个问题。
- 新增行为应补充自动化测试。
- 需要外部服务时，优先使用伪造客户端测试，不在 CI 中消耗真实额度。
- 文档中的能力描述必须与实际代码和验证记录一致。
