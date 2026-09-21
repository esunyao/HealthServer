# NutriMemo — AI 工作指南（导航）

> 本文件只做导航与理解，不新增规范；规范来源是根 [`AGENTS.md`](../AGENTS.md) 与 [`doc/README.md`](./doc/README.md)。行为、接口、配置与安全结论以源码、[`openapi.yaml`](./openapi.yaml)、契约与测试为准。

## 这个模块是什么

**营养膳食核心业务**（相当于剔除 AI 的营养后端）：拍照膳食记录服务（默认端口 `8099`）。客户端创建采集会话、Presigned URL 直传图片、确认后显式提交识别；AI 分析通过 Kafka 异步交给 HealthMind，结果事件写回餐次。

边界：
- owns：采集会话与图片确认、餐次记录、营养结果落库（AI 结果与人工修正）、日汇总与趋势、面向 HealthMind 的采集上下文。
- not owns：AI 分析与模型调用（HealthMind）、Dify 工作流、用户画像（Orion）、认证签发（Authentik）。

## 快速事实

| 项 | 值 |
|---|---|
| Gradle | `:nutrimemo` |
| 入口 | [`NutriMemoApplication.kt`](./src/main/kotlin/cn/esuny/nutrimemo/NutriMemoApplication.kt)（`@EnableScheduling`） |
| 端口 | `${SERVER_PORT:8099}` |
| 技术栈 | WebMVC（Servlet）+ PostgreSQL（`nutri` schema）+ Kafka + S3 兼容对象存储（客户端直传） |
| 配置来源 | [`application.yaml`](./src/main/resources/application.yaml)；Nacos `NutriMemo_Application.yaml`（group `NUTRIMEMO_GROUP`） |
| 迁移 | [`db/migration/V1__create_nutri_data_collection.sql`](./src/main/resources/db/migration/V1__create_nutri_data_collection.sql)（10 张表 + 11 条营养素种子）、[`V2__enable_kafka_delivery.sql`](./src/main/resources/db/migration/V2__enable_kafka_delivery.sql)（outbox `publishing`/`locked_at`、inbox `attempt_count`） |
| 契约 | [`openapi.yaml`](./openapi.yaml) v2.0.0；跨服务事件见 [../integration-contracts/AGENTS.md](../integration-contracts/AGENTS.md) |
| Kafka 消费 | `enable-auto-commit: false`、`ack-mode: record`、消费组 `nutrimemo-analysis-result-v1` |
| 持久层 | 主体是 [`persistence/NutriRepository.kt`](./src/main/kotlin/cn/esuny/nutrimemo/persistence/NutriRepository.kt)（JdbcTemplate 手写 SQL）；MyBatis-Plus 仅用于 ID/配置 |

## 代码地图

| 位置 | 职责 |
|---|---|
| [`controller/NutriController.kt`](./src/main/kotlin/cn/esuny/nutrimemo/controller/NutriController.kt) | 全部对外 REST handler（薄控制器） |
| [`service/NutriService.kt`](./src/main/kotlin/cn/esuny/nutrimemo/service/NutriService.kt) | 业务核心：会话生命周期、presign/confirm、提交、餐次 CRUD、汇总、过期清理 |
| [`integration/`](./src/main/kotlin/cn/esuny/nutrimemo/integration/) | `NutriOutboxPublisher`（发布）、`NutritionAnalysisResultListener`（消费）、`NutritionAnalysisResultService`（inbox 幂等 + 回写）、`AiWritebackPolicy`、`NutritionResultRepository`、`CanonicalEventJson` |
| [`internal/`](./src/main/kotlin/cn/esuny/nutrimemo/internal/) | `CaptureAnalysisContext`（供 HealthMind 读取已确认图片与餐次上下文）+ `NutriInternalSecurityConfig`（独立 M2M 安全链） |
| [`identity/CurrentUserArgumentResolver.kt`](./src/main/kotlin/cn/esuny/nutrimemo/identity/CurrentUserArgumentResolver.kt) | 从 Gateway 头解析当前用户 |
| [`config/`](./src/main/kotlin/cn/esuny/nutrimemo/config/) | `FlywayConfig`（独占 `nutri` schema）、`CaptureProperties`（TTL 24h、草稿上限 5、清理 15m）、`OssConfig/OssProperties`、`WebMvcConfig`、`MyBatisPlusConfig` |
| [`persistence/`](./src/main/kotlin/cn/esuny/nutrimemo/persistence/) | JdbcTemplate 仓储、`PgUuidTypeHandler` |

## 任务 → 读什么

| 你要做的事 | 先读 |
|---|---|
| 改采集/上传流程 | [`service/NutriService.kt`](./src/main/kotlin/cn/esuny/nutrimemo/service/NutriService.kt) → [`controller/NutriController.kt`](./src/main/kotlin/cn/esuny/nutrimemo/controller/NutriController.kt) → [`openapi.yaml`](./openapi.yaml) |
| 改提交事务（meal+outbox） | `NutriService.kt` 提交段 + [`persistence/NutriRepository.kt`](./src/main/kotlin/cn/esuny/nutrimemo/persistence/NutriRepository.kt)`insertOutbox`（`jsonb_build_object` 构造事件） |
| 改事件发布 | [`integration/NutriOutboxPublisher.kt`](./src/main/kotlin/cn/esuny/nutrimemo/integration/NutriOutboxPublisher.kt) + [../integration-contracts/AGENTS.md](../integration-contracts/AGENTS.md) |
| 改结果回写 | [`integration/NutritionAnalysisResultService.kt`](./src/main/kotlin/cn/esuny/nutrimemo/integration/NutritionAnalysisResultService.kt) + [`integration/AiWritebackPolicy.kt`](./src/main/kotlin/cn/esuny/nutrimemo/integration/AiWritebackPolicy.kt) |
| 改内部上下文接口 | [`internal/CaptureAnalysisContext.kt`](./src/main/kotlin/cn/esuny/nutrimemo/internal/CaptureAnalysisContext.kt) + `NutriInternalSecurityConfig.kt` |
| 排查分析链路卡住 | [../HealthMindControl/doc/analysis-chain.md](../HealthMindControl/doc/analysis-chain.md) 的「故障定位顺序」 |
| 改数据模型/表 | `db/migration/` 下迁移 + `persistence/NutriRepository.kt` + [`model/NutriModels.kt`](./src/main/kotlin/cn/esuny/nutrimemo/model/NutriModels.kt) |

## 关键事实与易错点

- **用户侧没有 Spring Security**：`identity/CurrentUserArgumentResolver` 直接信任 Gateway 注入的 `X-Gateway-Source: HealthServer-Gateway` 与 `X-Auth-Subject`。绕过 Gateway 直连本服务即等于绕过认证——安全前提是网络边界，改动此处要极度谨慎。
- **会话状态机**（V1 迁移）：`created → uploading → ready_for_analysis → analysing → completed / failed / expired / cancelled`；`meal_records.analysis_status`：`queued → analysing → completed/failed`。
- **提交事务**：submit 要求至少 1 张 `confirmed` 图片；同一事务写 `meal_records(queued)` + `meal_capture_sessions(ready_for_analysis)` + `integration_outbox(pending)`，并重算日汇总。
- **图片直传**：槽位 1–10（可复用 deleted 槽），对象键 `nutri/{userId}/capture/{sessionId}/{uuid}.{ext}`；presign 5 分钟、最大 10 MiB、jpeg/png/webp；confirm 用 `headObject` 校验类型与大小。
- **Outbox 发布器**：1s 轮询 `FOR UPDATE SKIP LOCKED`，发布成功后联动把会话置 `analysing`；发布失败置 `failed` 并设置重试时间。`published` 只代表 Broker 收到，不代表 HealthMind 已消费。
- **结果回写有保护策略**（`AiWritebackPolicy`）：餐食已删除→忽略；存在人工修正→保留人工值；否则应用 AI 结果。改动回写逻辑先读这个策略类。
- **消费幂等**：先按 `event_id` 走 inbox（冲突即跳过），再校验 `producer == "HealthMind"` 与 `subject_id` 归属；失败事件不会覆盖用户数据。
- MyBatis-Plus 出现在 `build.gradle` 但持久层主体是 JdbcTemplate——不要据此推断 ORM 用法。

## 接口与契约

- 对外：`/v1/nutri/capture-policy`、`/v1/nutri/capture-sessions/**`（创建/草稿/查询/取消/presign/confirm/删除图片/submit/retry）、`/v1/nutri/meals/**`、`/v1/nutri/summaries/**`；契约以 [`openapi.yaml`](./openapi.yaml) 为准（有 `OpenApiContractTest` 守护）。
- 内部：`/internal/v1/analysis-context/capture`（POST，M2M，scope `nutrimemo.ai-context.read`，校验 `azp == healthmind-nutrimemo`），不经 Gateway。
- 事件：生产 `nutrition.capture.ready.v1`（Kafka key = captureSessionId）；消费 `nutrition.analysis.completed.v1` / `nutrition.analysis.failed.v1`。契约单一来源在 `integration-contracts` 模块。

## 测试与验证

```bash
./gradlew :nutrimemo:test
./gradlew :nutrimemo:bootRun   # 需要 PostgreSQL、Kafka、Nacos、Authentik 与 S3 兼容对象存储
```

- 测试在 [`src/test/kotlin/cn/esuny/nutrimemo/`](./src/test/kotlin/cn/esuny/nutrimemo/)：契约（`OpenApiContractTest`）、迁移脚本、校验、身份解析、写回策略、结果服务、Kafka 契约、检索过滤。
- 改动提交事务、发布器、回写策略或 API 时补聚焦测试。

## 相关文档

- [doc/README.md](./doc/README.md) — 模块公开大体说明（主流程与接口范围）。
- [../AGENTS.md](../AGENTS.md) — 仓库规范、阅读导航与项目背景。
- [../integration-contracts/AGENTS.md](../integration-contracts/AGENTS.md)、[../HealthMind/AGENTS.md](../HealthMind/AGENTS.md) — 链路对端。
- 私有：`doc-project/`（背景与时序，不提交）；`docp/`（若存在，只读参考、不写入）。
