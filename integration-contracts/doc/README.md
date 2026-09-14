# integration-contracts — 模块大体说明

HealthServer 的跨服务事件契约来源。它不是可部署服务，只提供 JSON Schema、AsyncAPI 描述和对应的 Kotlin 数据类。

NutriMemo 和 HealthMind 共享本模块；修改事件结构时，应同时检查 schema、AsyncAPI、Kotlin 类型和两个消费/发布方。

## 契约文件

| 文件 | 内容 |
|---|---|
| `src/main/resources/schema/nutrition-capture-ready-v1.schema.json` | 采集完成事件 |
| `src/main/resources/schema/nutrition-analysis-completed-v1.schema.json` | 分析成功事件 |
| `src/main/resources/schema/nutrition-analysis-failed-v1.schema.json` | 分析失败事件 |
| `src/main/resources/asyncapi/nutrition-analysis-v1.yaml` | AsyncAPI 3.0 收发描述 |
| `src/main/kotlin/cn/esuny/contracts/integration/v1/IntegrationEvents.kt` | Kotlin 事件类型和数据类 |

## 事件

| 逻辑 event_type | 方向 |
|---|---|
| `nutrition.capture.ready.v1` | NutriMemo → HealthMind |
| `nutrition.analysis.completed.v1` | HealthMind → NutriMemo |
| `nutrition.analysis.failed.v1` | HealthMind → NutriMemo |

物理 topic 使用短横线，例如 `nutrition-capture-ready`；逻辑 `event_type` 使用点号和版本。两者不是同一个字符串。

事件信封中的 `aggregate_id` 是 meal ID。NutriMemo 数据库 outbox 的内部 `aggregate_id` 是 capture session UUID，并作为该发布器的 Kafka key；阅读实现时不能将两者混称。

跨语言序列化必须保持 UUID、时间和大整数的契约精度；具体字段约束以 JSON Schema 为准。

## 验证

```bash
./gradlew :integration-contracts:test
./gradlew :integration-contracts:build
```