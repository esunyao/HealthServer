# integration-contracts — AI 工作指南（导航）

> 本文件只做导航与理解，不新增规范；规范来源是根 [`AGENTS.md`](../AGENTS.md) 与 [`doc/README.md`](./doc/README.md)。事件字段约束以 JSON Schema 为准，Kotlin 类型以源码为准。

## 这个模块是什么

**跨服务事件契约的单一来源**（非可部署服务）：只提供 JSON Schema、AsyncAPI 描述和对应的 Kotlin 数据类。NutriMemo 与 HealthMind 共享本模块。

边界：
- owns：事件信封与 payload 的类型定义、Schema、AsyncAPI 描述。
- not owns：物理 Kafka topic 命名与消费组（部署配置）；具体发送/接收实现（在 NutriMemo 与 HealthMind）。

## 快速事实

| 项 | 值 |
|---|---|
| Gradle | `:integration-contracts`（`bootJar` 禁用、`jar` 启用，见 [`build.gradle`](./build.gradle)） |
| 唯一源码 | [`src/main/kotlin/cn/esuny/contracts/integration/v1/IntegrationEvents.kt`](./src/main/kotlin/cn/esuny/contracts/integration/v1/IntegrationEvents.kt) |
| Schema | [`src/main/resources/schema/`](./src/main/resources/schema/)：`nutrition-{capture-ready,analysis-completed,analysis-failed}-v1.schema.json`（`$id` 命名空间 `https://healthmind.local/schema/...`） |
| AsyncAPI | [`src/main/resources/asyncapi/nutrition-analysis-v1.yaml`](./src/main/resources/asyncapi/nutrition-analysis-v1.yaml)（AsyncAPI 3.0.0，「HealthMind Nutrition Analysis Events」v1.0.0） |
| 依赖 | `api jackson-annotations`；无 Nacos/Kafka/数据库依赖 |
| 使用方 | NutriMemo（生产 capture-ready；消费 completed/failed）与 HealthMind（消费 capture-ready；生产 completed/failed） |

## 契约内容

事件类型常量（`NutritionEventTypes`）：`nutrition.capture.ready.v1`、`nutrition.analysis.completed.v1`、`nutrition.analysis.failed.v1`；`SCHEMA_VERSION = "1.0"`。

泛型信封 `IntegrationEvent<T>` 字段：`event_id`、`event_type`、`occurred_at`、`producer`、`trace_id`、`subject_id`、`aggregate_type`、`aggregate_id`、`schema_version`、`payload`（序列化为 snake_case）。

Payload：
- `NutritionCaptureReadyPayload`：`capture_session_id`、`meal_id`。
- `NutritionAnalysisCompletedPayload`：`task_id`、`result_version`、`overall_confidence`、`items: List<AnalyzedMealItem>`（含 `List<AnalyzedNutrient>`）。
- `NutritionAnalysisFailedPayload`：`error_code`、`failure_category`、`retryable`、`error_summary`。

## 任务 → 读什么

| 你要做的事 | 先读 |
|---|---|
| 改事件字段 | [`IntegrationEvents.kt`](./src/main/kotlin/cn/esuny/contracts/integration/v1/IntegrationEvents.kt) → 对应 schema → AsyncAPI → 两端模块 AGENTS.md（[../NutriMemo/AGENTS.md](../NutriMemo/AGENTS.md)、[../HealthMind/AGENTS.md](../HealthMind/AGENTS.md)） |
| 新增事件 | 三个文件全套新增（Kotlin 常量+数据类、schema、AsyncAPI channel/operation），并更新 [doc/README.md](./doc/README.md) 的表 |
| 排查跨服务不一致 | 先核对本模块 schema 与 Kotlin 类型，再看两端实现（有 `OpenApiContractTest`/`NutritionKafkaContractTest` 等守护） |

## 关键事实与易错点

- **逻辑 event_type ≠ 物理 topic**：`event_type` 用点号+版本（如 `nutrition.capture.ready.v1`）；物理 topic 用短横线（如 `nutrition-capture-ready`），且 AsyncAPI 里是**参数化地址**（`{captureReadyDestination}` 等）——物理名称属于部署配置，不要写死或混称。
- **`aggregate_id` 双重含义**：事件信封中 `aggregate_id` 是 meal ID；NutriMemo outbox 内部的 `aggregate_id` 是 capture session UUID（并作为 Kafka key）。阅读实现时不能混称。
- **`schema_version` 与文件名**：`SCHEMA_VERSION = "1.0"`，文件名后缀 `v1` 指事件契约主版本；两者不是同一套编号体系。
- **修改必须同步三处**：Kotlin 类型、JSON Schema、AsyncAPI——并检查 NutriMemo 与 HealthMind 两个消费/发布方；只改一处会造成跨语言运行期不一致。
- **序列化精度**：跨语言必须保持 UUID、时间与大整数的契约精度（Jackson 默认 snake_case，见测试 `IntegrationEventsTest`）。

## 测试与验证

```bash
./gradlew :integration-contracts:test
./gradlew :integration-contracts:build
```

- 唯一测试 [`IntegrationEventsTest.kt`](./src/test/kotlin/cn/esuny/contracts/integration/v1/IntegrationEventsTest.kt)：验证 snake_case 序列化与 `schema_version` 默认值。
- 改动契约后，除本模块外还应运行两端模块测试（`./gradlew :nutrimemo:test :healthmind:test`）。

## 相关文档

- [doc/README.md](./doc/README.md) — 契约文件表与事件方向。
- [../AGENTS.md](../AGENTS.md) — 仓库规范（跨服务链路阅读入口在这里指向本模块）。
- [../NutriMemo/AGENTS.md](../NutriMemo/AGENTS.md)、[../HealthMind/AGENTS.md](../HealthMind/AGENTS.md) — 实现端导航。
- [../HealthMindControl/doc/analysis-chain.md](../HealthMindControl/doc/analysis-chain.md) — 含 Kafka topic 的端到端时序。
- 私有：`doc-project/`（背景与规范，不提交）；`docp/`（若存在，只读参考、不写入）。
