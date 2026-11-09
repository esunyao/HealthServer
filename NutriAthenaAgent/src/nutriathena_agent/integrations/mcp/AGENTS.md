# HealthMind MCP 导航

父级导航：[`../AGENTS.md`](../AGENTS.md)。

- [`client.py`](client.py)：OAuth、SDK 会话生命周期、capture 一次预取、连接阶段与异常链。
- [`context.py`](context.py)：capture 契约、SDK/JSON 结果解析、敏感字段过滤和上下文大小限制。
- [`tools.py`](tools.py)：稳定 `_meta.tool_call_id`、只读工具匹配、每 attempt 调用限制与预取缓存。
- [`__init__.py`](__init__.py)：供 runner 和兼容调用方使用的统一导出入口。
- 回归测试：[`../../../../tests/integrations/`](../../../../tests/integrations/)。
