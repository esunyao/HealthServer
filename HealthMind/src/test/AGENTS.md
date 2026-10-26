# HealthMind tests

上级规范与导航：[根 AGENTS.md](../../../AGENTS.md) · [模块 AGENTS.md](../../AGENTS.md) · [公开说明](../doc/README.md)

本目录只负责测试导航：

- 任务状态机与 Agent 客户端测试位于 `kotlin/cn/esuny/healthmind/application/service`、`infrastructure/agent`。
- PostgreSQL、Flyway、outbox、lease 和 MCP 授权测试位于 `infrastructure/database`。
- Agent Protocol HTTP 契约应读取 `integration-contracts/src/main/resources/agent-protocol/v1/` 的共享夹具，不维护第二份响应样例。
- Testcontainers 测试依赖可用 Docker engine；不可用时必须明确报告未验证，不能用单元测试代替数据库迁移验证。
- 不读取真实 `.env`，不打印凭据、签名 URL 或真实餐食内容。

