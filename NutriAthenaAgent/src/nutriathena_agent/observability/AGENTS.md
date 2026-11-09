# Observability 导航

上级导航：[../AGENTS.md](../AGENTS.md)。公开接口集中在 [__init__.py](__init__.py)。

| 任务 | 入口 |
|---|---|
| 调试级别、日志格式与环境值解析 | [levels.py](levels.py) |
| 文本、结构化字段与凭据脱敏 | [redaction.py](redaction.py) |
| 异常链、ExceptionGroup 与 ValidationError 摘要 | [exceptions.py](exceptions.py) |
| 文本、扁平 JSON、内容块与终端颜色 | [formatting.py](formatting.py) |
| 上下文、Loguru sink、stdlib 接管与重置 | [logging.py](logging.py) |
| opt-in 调试事件与内容 | [tracer.py](tracer.py) |
| LangChain 节点、模型、工具回调 | [callback.py](callback.py) |
| 离线验证与待接线集成断言 | [tests/observability](../../../tests/observability/AGENTS.md) |
