# Observability 测试导航

上级导航：[../AGENTS.md](../AGENTS.md)。实现入口：[observability](../../src/nutriathena_agent/observability/AGENTS.md)。

| 文件 | 验证内容 |
|---|---|
| [conftest.py](../conftest.py) | 新日志实现与 stdlib 全局状态的测试隔离 |
| [test_logging.py](test_logging.py)、[test_levels.py](test_levels.py) | 原日志格式、颜色、文件 sink、级别解析断言 |
| [test_tracer.py](test_tracer.py)、[test_callback.py](test_callback.py) | 原 tracer 与 LangChain 回调断言 |
| [test_context.py](test_context.py) | 嵌套、并发 asyncio、线程和取消后的上下文隔离 |
| [test_exceptions.py](test_exceptions.py) | 异常链、ExceptionGroup、验证输入脱敏与 stdlib 异常 |
| [test_redaction.py](test_redaction.py) | 凭据、图片 URL、嵌套结构化字段和终端转义脱敏 |
| [test_state.py](test_state.py) | 重配、恢复、调用位置、导入独立性与外部日志状态 |
| [test_integration.py](test_integration.py) | 配置级别身份、CLI debug 优先级、MockTransport OAuth 根因 |

`test_integration.py` 的最终 CLI 入口是 `nutriathena_agent.cli.commands`，meal 替身入口是 `nutriathena_agent.meal.runner.run_meal_analysis`。独立工作树尚未集成 CLI 时，CLI 断言显示 skip；配置断言需要 config 统一导入 observability 的 `DebugLevel`。OAuth 测试暂用旧 `mcp_tools`，集成后随对应包的迁移调整。
