# integration-contracts tests

上级规范与导航：[根 AGENTS.md](../../../AGENTS.md) · [模块 AGENTS.md](../../AGENTS.md) · [公开说明](../doc/README.md)

本目录只负责测试导航：

- `kotlin/cn/esuny/contracts/integration/v1/` 验证事件序列化和 Schema/AsyncAPI 的同步关系。
- Agent Protocol 共享夹具位于 `src/main/resources/agent-protocol/v1/`，HealthMind 与 NutriAthenaAgent 必须消费同一组夹具。
- 新增事件必须同时提交 Kotlin 类型、JSON Schema、AsyncAPI 和两侧消费/生产测试。
- 不使用真实 Kafka、OAuth、数据库或模型。

