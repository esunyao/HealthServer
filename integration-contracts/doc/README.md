# integration-contracts — 模块大体说明

HealthServer 的跨服务契约来源。它不是可部署服务，提供 Kafka 事件 JSON Schema、AsyncAPI、对应 Kotlin 数据类，以及 HealthMind 与 NutriAthenaAgent 共用的 Agent Protocol HTTP Schema 和示例夹具。

NutriMemo、HealthMind 与 NutriAthenaAgent 共享本模块；修改契约时应同时检查 Schema、AsyncAPI、类型和所有生产/消费方。

## 契约文件

| 文件 | 内容 |
|---|---|
| `src/main/resources/schema/nutrition-capture-ready-v1.schema.json` | 采集完成事件 |
| `src/main/resources/schema/nutrition-analysis-completed-v1.schema.json` | 分析成功事件 |
| `src/main/resources/schema/nutrition-analysis-failed-v1.schema.json` | 分析失败事件 |
| `src/main/resources/schema/nutrition-analysis-review-required-v1.schema.json` | 需要人工复核事件 |
| `src/main/resources/asyncapi/nutrition-analysis-v1.yaml` | AsyncAPI 3.0 收发描述 |
| `src/main/kotlin/cn/esuny/contracts/integration/v1/IntegrationEvents.kt` | Kotlin 事件类型和数据类 |
| `src/main/resources/agent-protocol/v1/` | Agent Thread/Run HTTP Schema 与共享示例 |

## 事件

| 逻辑 event_type | 方向 |
|---|---|
| `nutrition.capture.ready.v1` | NutriMemo → HealthMind |
| `nutrition.analysis.completed.v1` | HealthMind → NutriMemo |
| `nutrition.analysis.failed.v1` | HealthMind → NutriMemo |
| `nutrition.analysis.review_required.v1` | HealthMind → NutriMemo |

物理 topic 使用短横线，例如 `nutrition-capture-ready`；逻辑 `event_type` 使用点号和版本。两者不是同一个字符串。AsyncAPI 中的地址是参数化占位符，物理名称属于部署配置。

Schema 的 `$id` 统一使用 `https://healthmind.local/schema/...` 命名空间；信封 `schema_version` 固定为 `"1.0"`，文件名后缀 `v1` 表示事件契约主版本，两者不是同一套编号。

事件信封中的 `aggregate_id` 是 meal ID。NutriMemo 数据库 outbox 的内部 `aggregate_id` 是 capture session UUID，并作为该发布器的 Kafka key；阅读实现时不能将两者混称。

跨语言序列化必须保持 UUID、时间和大整数的契约精度；具体字段约束以 JSON Schema 为准。

## Agent Protocol

HealthMind 与 NutriAthenaAgent 的 Thread/Run 字段以 `agent-protocol/v1/` 为准。Thread 响应必须包含 `thread_id` 与 `metadata.task_id/attempt_id`；不可只在各自测试中维护 mock 样例。详见 [agent-protocol.md](./agent-protocol.md)。

## 验证

```bash
./gradlew :integration-contracts:test
./gradlew :integration-contracts:build
cd NutriAthenaAgent && uv run pytest -q
```

## 进一步阅读

- [模块 AGENTS.md](../AGENTS.md)：AI 导航（契约内容、任务 → 读什么、易错点）。
- [Agent Protocol](./agent-protocol.md)：HealthMind 与 NutriAthenaAgent 的共享 HTTP 契约。
- [根 AGENTS.md](../../AGENTS.md)：仓库规范、阅读导航与跨服务链路入口。
- [NutriMemo/AGENTS.md](../../NutriMemo/AGENTS.md) 与 [HealthMind/AGENTS.md](../../HealthMind/AGENTS.md)：契约的消费/发布实现端。