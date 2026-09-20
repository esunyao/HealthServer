# HealthMind — 模块大体说明

HealthServer 的 AI 编排服务（默认端口 `8100`）。它管理分析任务、工作流版本、契约校验、Kafka 投递、MCP 工具授权和审计状态。

HealthMind 不拥有用户健康记录、餐食记录、图片、Prompt、知识库、模型路由或 vLLM 生命周期；这些属于 Orion、NutriMemo、Dify 或部署平台。

## 技术栈

| 组件 | 说明 |
|---|---|
| Web | Spring WebMVC |
| MCP | Spring AI MCP Server，`STREAMABLE`，端点 `/mcp` |
| 数据库 | PostgreSQL，`healthmind` schema；Flyway 管理结构 |
| 消息 | Kafka，inbox / outbox 模式 |
| 工作流 | Dify Workflow blocking 调用 |
| 认证 | Authentik OIDC Resource Server 与 M2M client credentials |

所有服务地址、issuer 和凭据均由环境变量或 Nacos 注入。

## MCP 工具

| 工具 | 用途 |
|---|---|
| `nutrimemo.capture_context.get` | 读取已确认图片与餐次元数据，并以 MCP `ImageContent` 返回真实图片文件 |
| `orion.nutrition_context.get` | 读取经授权的最小营养健康上下文 |

工具调用以任务和 attempt 作为上下文；调用方不能自由指定用户、采集会话或餐次。工具仅返回当前任务授权范围内的数据。

`nutrimemo.capture_context.get` 会在响应 Schema 校验通过后，按 `image_urls` 顺序下载全部图片。MCP 响应的 `content` 只包含图片，`structuredContent` 保留餐次元数据；因此 Dify 1.17.1 中对应为 `files` 与 `json`，`text` 为空。任意图片下载失败都会使整次工具调用失败，不会返回部分图片。

图片下载不经过服务发现，默认仅允许 JPEG、PNG 和 WebP，最多 10 张、单张最多 10 MiB、总计最多 100 MiB。可通过以下环境变量调整：

- `HEALTHMIND_MCP_CAPTURE_IMAGE_MAX_COUNT`
- `HEALTHMIND_MCP_CAPTURE_IMAGE_MAX_BYTES`
- `HEALTHMIND_MCP_CAPTURE_IMAGE_MAX_TOTAL_BYTES`
- `HEALTHMIND_MCP_CAPTURE_IMAGE_ALLOWED_MIME_TYPES`

失败信息和日志不会包含完整预签名 URL；工具调用审计只保存上下文 JSON 的 SHA-256，不保存图片 Base64。

## 事件与工作流

- 消费 `nutrition.capture.ready.v1`，并发布 `nutrition.analysis.completed.v1` 或 `nutrition.analysis.failed.v1`。
- 接收事件时固定当时的 production Workflow Release；运行中和重试任务不切换到新版本。
- Release 提升脚本位于 `src/main/resources/db/manual/promote_workflow_release.sql`。
- 结构化结果和集成记录默认保留 30 天，任务与工具审计默认保留 180 天。

## 代码位置

- `application/`：任务执行服务和出站端口。
- `domain/task/`：任务领域模型。
- `infrastructure/database/`：任务、工具调用、恢复和保留策略。
- `infrastructure/dify/`、`infrastructure/http/`：Dify 与内部上下文客户端。
- `infrastructure/messaging/`、`interfaces/messaging/`：outbox 和 Kafka listener。
- `interfaces/mcp/`：HealthMind MCP 工具。

## 验证

```bash
./gradlew :healthmind:test
./gradlew :healthmind:bootRun
```

`bootRun` 需要 PostgreSQL、Kafka、Nacos、Authentik 和 Dify 的环境配置。