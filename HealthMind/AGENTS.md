# HealthMind — AI 工作指南（导航）

> 本文件只做导航与理解，不新增规范；规范来源是根 [`AGENTS.md`](../AGENTS.md) 与 [`doc/README.md`](./doc/README.md)。行为、接口、配置与安全结论以源码、配置、契约与测试为准。

## 这个模块是什么

**AI 能力层（AI 编排服务）**（默认端口 `8100`）：管理分析任务、工作流版本、契约校验、Kafka 投递、MCP 工具授权和审计状态。六边形（端口/适配器）分层。

边界：
- owns：任务与 attempt 状态机、工作流 release 绑定、Dify 工作流调用编排、结果 JSON Schema 校验、Inbox/Outbox、MCP 工具授权与调用审计。
- not owns：用户健康记录、餐食记录、图片（Orion / NutriMemo）；Prompt、知识库、模型路由、vLLM 生命周期（Dify 或部署平台）。

## 快速事实

| 项 | 值 |
|---|---|
| Gradle | `:healthmind` |
| 入口 | [`HealthMindApplication.kt`](./src/main/kotlin/cn/esuny/healthmind/HealthMindApplication.kt) |
| 端口 | `${HEALTHMIND_PORT:8100}` |
| 技术栈 | WebMVC + Spring AI MCP Server（`STREAMABLE`，端点 `/mcp`，spring-ai-bom 2.0.0）+ PostgreSQL（`healthmind` schema）+ Kafka + Dify Workflow（blocking） |
| 配置来源 | [`application.yaml`](./src/main/resources/application.yaml)；Nacos `HealthMind_Application.yaml`；业务配置集中在 `healthmind.*`（[`HealthMindProperties.kt`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/config/HealthMindProperties.kt)） |
| 迁移 | [`db/migration/`](./src/main/resources/db/migration/)：V1 schema（12 张表）、V2 稳定定义种子（任务类型 `nutrition.meal_analysis` + 两个工具定义含内嵌 JSON Schema 与 sha256）、V3 审计 action `tools_bound` |
| release 提升 | [`db/manual/promote_workflow_release.sql`](./src/main/resources/db/manual/promote_workflow_release.sql)（psql 变量驱动；咨询锁 + candidate→production、旧 production→retired + 审计）——**手动脚本，不随 Flyway 自动执行** |
| 业务 API | 无 REST 业务 API、无 `openapi.yaml`；业务入口是 MCP `/mcp` |
| 保留期 | 结果与集成记录默认 30 天，任务与工具审计默认 180 天（`healthmind.*.retention`） |

## 代码地图（六边形分层）

| 层 | 位置 | 职责 |
|---|---|---|
| application | [`application/service/TaskExecutionService.kt`](./src/main/kotlin/cn/esuny/healthmind/application/service/TaskExecutionService.kt) | `@Scheduled` 每 1s `claimNext()` → 调 Dify → 输出 schema 校验 → complete/fail |
| application | [`application/port/out/`](./src/main/kotlin/cn/esuny/healthmind/application/port/out/) | 出站端口：`DifyWorkflowPort`、`InternalContextPort` |
| domain | [`domain/task/TaskModels.kt`](./src/main/kotlin/cn/esuny/healthmind/domain/task/TaskModels.kt) | `TaskExecution`、`DifyWorkflowResult`、`FailureCategory`（TRANSIENT/PERMANENT/CONTRACT/TIMEOUT/CANCELLED） |
| infrastructure | [`infrastructure/database/TaskCommandRepository.kt`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/database/TaskCommandRepository.kt) | inbox 接收、任务认领、完成/失败、outbox 写入（事务核心） |
| infrastructure | [`infrastructure/database/ToolInvocationRepository.kt`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/database/ToolInvocationRepository.kt) | MCP 工具授权与 `ai_tool_invocations` 审计 |
| infrastructure | [`infrastructure/database/RecoveryAndRetentionJobs.kt`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/database/RecoveryAndRetentionJobs.kt) | 卡死 publishing/超时 attempt 恢复（每分钟）、每日 03:20 清理 |
| infrastructure | [`infrastructure/dify/DifyWorkflowClient.kt`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/dify/DifyWorkflowClient.kt) | Dify blocking 调用与错误分类 |
| infrastructure | [`infrastructure/http/InternalContextClient.kt`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/http/InternalContextClient.kt)、[`oauth/ClientCredentialsTokenProvider.kt`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/oauth/ClientCredentialsTokenProvider.kt) | 调 NutriMemo/Orion 内部接口的 M2M 客户端 |
| infrastructure | [`infrastructure/json/`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/json/) | `CanonicalJson`（键排序规范化 + SHA-256）、`JsonSchemaService`（networknt 校验） |
| infrastructure | [`infrastructure/messaging/HealthMindOutboxPublisher.kt`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/messaging/HealthMindOutboxPublisher.kt) | outbox 发布（1s 轮询、`SKIP LOCKED`、指数退避封顶 5 分钟） |
| interfaces | [`interfaces/mcp/HealthMindMcpTools.kt`](./src/main/kotlin/cn/esuny/healthmind/interfaces/mcp/HealthMindMcpTools.kt) | MCP 工具：`nutrimemo.capture_context.get`、`orion.nutrition_context.get` |
| interfaces | [`interfaces/messaging/NutritionCaptureReadyListener.kt`](./src/main/kotlin/cn/esuny/healthmind/interfaces/messaging/NutritionCaptureReadyListener.kt) | Kafka 入口事件监听（手动 ack） |
| config | [`infrastructure/config/`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/config/) | `HealthMindProperties`、`SecurityConfig`（MCP 安全+RFC 9728 元数据）、`FlywayConfig`（独占 `healthmind` schema）、`HttpClientConfig` |

## 任务 → 读什么

| 你要做的事 | 先读 |
|---|---|
| 改任务状态机/重试 | [`domain/task/TaskModels.kt`](./src/main/kotlin/cn/esuny/healthmind/domain/task/TaskModels.kt) → [`infrastructure/database/TaskCommandRepository.kt`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/database/TaskCommandRepository.kt) → [`application/service/TaskExecutionService.kt`](./src/main/kotlin/cn/esuny/healthmind/application/service/TaskExecutionService.kt) |
| 改 Dify 调用 | [`infrastructure/dify/DifyWorkflowClient.kt`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/dify/DifyWorkflowClient.kt) + `application.yaml` 的 `healthmind.dify.*` |
| 改 MCP 工具/授权 | [`interfaces/mcp/HealthMindMcpTools.kt`](./src/main/kotlin/cn/esuny/healthmind/interfaces/mcp/HealthMindMcpTools.kt) → [`infrastructure/database/ToolInvocationRepository.kt`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/database/ToolInvocationRepository.kt) → [`infrastructure/config/SecurityConfig.kt`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/config/SecurityConfig.kt) |
| 改结果契约/校验 | [`infrastructure/json/JsonSchemaService.kt`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/json/JsonSchemaService.kt) + [../integration-contracts/AGENTS.md](../integration-contracts/AGENTS.md) + 私有（仓库根）`doc-project/0917Dify餐食AI结构化输出规范.md` |
| 改事件进出 | [`interfaces/messaging/NutritionCaptureReadyListener.kt`](./src/main/kotlin/cn/esuny/healthmind/interfaces/messaging/NutritionCaptureReadyListener.kt)、[`infrastructure/messaging/HealthMindOutboxPublisher.kt`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/messaging/HealthMindOutboxPublisher.kt) |
| 发布新工作流版本 | [`db/manual/promote_workflow_release.sql`](./src/main/resources/db/manual/promote_workflow_release.sql)（手动脚本，注意咨询锁与审计） |
| 排查链路卡住 | [../HealthMindControl/doc/analysis-chain.md](../HealthMindControl/doc/analysis-chain.md) 的「故障定位顺序」+ [`RecoveryAndRetentionJobs.kt`](./src/main/kotlin/cn/esuny/healthmind/infrastructure/database/RecoveryAndRetentionJobs.kt) |

## 关键事实与易错点

- **任务状态机**：`ai_tasks.status ∈ {queued, running, succeeded, failed, cancelled, expired}`（V1 CHECK 约束）；代码实际写入路径是 `queued → running → succeeded/failed`，可重试失败回 `queued`（退避 `5s × 2^(n-1)`，封顶 20s，加 0–1s 抖动）。`expired`/`cancelled` 在 schema 存在但**当前代码无写入路径**，不要据此假设行为。
- **attempt 状态**：`{pending, running, succeeded, failed, timed_out, cancelled}`；attempt 数据库超时一小时，恢复任务只恢复最新 attempt。
- **MCP 双层授权**：JWT 层（`SecurityConfig`）要求 issuer + audience `healthmind-mcp` + `azp == dify-healthmind`，并发布 RFC 9728 protected resource metadata（scope `healthmind.tool.nutrimemo.capture-context.read`、`healthmind.tool.orion.nutrition-context.read`）；工具层（`ToolInvocationRepository.authorizeAndStart`）要求任务/attempt 为 running、release 已绑定该工具、调用方 scope 与 `allowed_scope` 匹配、未超 `max_calls`，随后写 `ai_tool_invocations`（含请求/响应 sha256 审计）。调用方只能传 `taskId`/`attemptId`。
- **Release 固定语义**：接收事件时固定当时的 production Workflow Release；运行中和重试任务不切换到新版本。改任务流程时不要引入"实时取最新版本"。
- **Dify 调用细节**：`POST {baseUrl}/workflows/{workflowId}/run`、`response_mode=blocking`；inputs 只有 `task_id`/`attempt_id`/`trace_id`（上下文由 Dify 经 MCP 回拉）；`user` 是 taskId 的 SHA-256 截断伪名 `hm-<24hex>`；超时 connect 3s / read 130s；错误分类 429/5xx→transient、401/403/404→permanent、超时→timeout。
- **App Key 注入**：`healthmind.dify.app-keys` 是 `dify_app_id → api_key` 映射，由环境变量 `DIFY_APP_KEY_1`/`DIFY_API_KEY_1` 等注入，**密钥不入库**。
- **Inbox 幂等**：`acceptCaptureReady` 用 `ON CONFLICT DO NOTHING`；同事务新建 `queued` 任务并把 inbox 标 `processed`；无 production release 时抛异常，listener `nack(30s)` 延迟重试（重投不会重置已有 inbox）。
- **结果哈希**：`CanonicalJson` 对键排序后 SHA-256，用于 result hash 与工具调用审计；改输出结构时注意规范化不受字段顺序影响。

## 接口与契约

- MCP：`/mcp`（STREAMABLE）；工具 `nutrimemo.capture_context.get`、`orion.nutrition_context.get`。
- 其他端点：Actuator（health/info/metrics/prometheus）、`/.well-known/oauth-protected-resource/**`。
- Kafka：消费物理 topic `nutrition-capture-ready`（对应 `event_type` = `nutrition.capture.ready.v1`；校验 `event_type`/`schema_version`/`producer == "NutriMemo"`/`aggregate_type == "meal"`，消费组 `healthmind-nutrition-v1`）；生产 `nutrition-analysis-completed` / `nutrition-analysis-failed`（key = captureSessionId）。物理 topic 名与本模块 `doc/README.md` 使用的事件类型名是两套命名，勿混称。
- 事件契约单一来源：[../integration-contracts/AGENTS.md](../integration-contracts/AGENTS.md)。

## 测试与验证

```bash
./gradlew :healthmind:test
./gradlew :healthmind:bootRun   # 需要 PostgreSQL、Kafka、Nacos、Authentik 与 Dify
```

- 测试在 [`src/test/kotlin/cn/esuny/healthmind/`](./src/test/kotlin/cn/esuny/healthmind/)：迁移（脚本 + Testcontainers 集成）、OAuth 元数据、Dify 客户端（MockWebServer）、JSON 规范化与 schema、Kafka 监听。**MCP 工具层暂无测试**，改动工具授权要谨慎并考虑补测。
- 测试依赖：MockK、Testcontainers、MockWebServer。

## 相关文档

- [README.md](./README.md) — 模块根兼容入口（指向 `doc/README.md`）。
- [doc/README.md](./doc/README.md) — 模块公开大体说明（工具表、事件与保留期）。
- [../AGENTS.md](../AGENTS.md) — 仓库规范、阅读导航与项目背景（HealthMind 是通用 AI 能力层）。
- 链路对端：[../NutriMemo/AGENTS.md](../NutriMemo/AGENTS.md)、[../Orion/AGENTS.md](../Orion/AGENTS.md)、[../integration-contracts/AGENTS.md](../integration-contracts/AGENTS.md)。
- 链路状态与排障：[../HealthMindControl/doc/analysis-chain.md](../HealthMindControl/doc/analysis-chain.md)。
- 私有：`doc-project/`（Dify 输出规范与 m2m 时序，不提交）；`docp/`（若存在，只读参考、不写入）。
