# NutriAthenaAgent tests

上级规范与导航：[根 AGENTS.md](../../AGENTS.md) · [模块 AGENTS.md](../AGENTS.md) · [公开说明](../doc/README.md)

本目录只负责测试导航：

- `contract/` 读取 `integration-contracts/src/main/resources/agent-protocol/v1/` 的共享 HTTP 夹具。
- `test_runtime_api.py` 覆盖 Thread/Run HTTP 与鉴权；`test_worker.py` 覆盖租约和终态 fencing。
- `test_meal_agent.py` 覆盖视觉输入、备注、空证据、MCP 工具和输出契约。
- `test_postgres_runtime.py` 需要 Docker；跳过时必须报告。
- 默认测试不得连接真实 OAuth、MCP、模型或生产数据库，不得读取或打印 `.env`。

