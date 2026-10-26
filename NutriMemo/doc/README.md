# NutriMemo — 模块大体说明

HealthServer 的拍照膳食记录服务（默认端口 `8099`）。客户端创建采集会话、上传并确认图片后显式提交识别；AI 分析通过 Kafka 异步交给 HealthMind。

## 技术栈

| 组件 | 说明 |
|---|---|
| Web | Spring WebMVC（Servlet） |
| 数据库 | PostgreSQL，`nutri` schema；Flyway V3 增加 `needs_review` 与 `meal_analysis_reports` |
| 消息 | Kafka，outbox 发布与结果事件消费 |
| 对象存储 | S3 兼容协议，客户端通过 presigned URL 直传 |
| 契约 | `NutriMemo/openapi.yaml` v2.0.0 |

数据库、Kafka、Authentik 和对象存储地址只从环境变量或 Nacos 注入。

用户侧请求只信任 Gateway 注入的 `X-Gateway-Source: HealthServer-Gateway` 与 `X-Auth-Subject` 头；服务本身不校验用户令牌，绕过 Gateway 直连即绕过认证。

## 主流程

```text
创建采集会话 → 申请上传地址 → 上传并确认图片 → 提交餐食
  → 事务写入餐食与 capture-ready outbox → 发布 Kafka
  → HealthMind 执行分析 → 发布 completed / failed / review-required 结果
  → NutriMemo 消费结果并写回餐食营养数据
```

outbox 负责可靠发布；Kafka 是服务间事件通道。分析结果消费使用 `enable-auto-commit=false`，Spring listener 的确认模式是 `record`。

## 接口范围

- `/v1/nutri/capture-policy`：读取采集限制。
- `/v1/nutri/capture-sessions/**`：创建、查询、取消、上传确认、提交和重试采集会话（提交与重试返回 202，表示已进入异步分析）。
- `/v1/nutri/meals/**`：查询、修改和删除餐次。
- `/v1/nutri/summaries/**`：读取单日汇总和趋势。
- `/internal/v1/analysis-context/capture`：供 HealthMind 读取已确认图片与餐次上下文，不经 Gateway。

## 代码位置

- `controller/`：对外餐食和采集接口。
- `internal/CaptureAnalysisContext`：内部分析上下文端点及其安全边界。
- `integration/`：outbox 发布、分析结果消费和集成策略。
- `persistence/`、`service/`、`model/`：数据库访问、业务服务和数据模型。

## 验证

```bash
./gradlew :nutrimemo:test
./gradlew :nutrimemo:bootRun
```

`bootRun` 需要 PostgreSQL、Kafka、Nacos、Authentik 和 S3 兼容对象存储的环境配置。

`GET /v1/nutri/meals/{mealId}` 是结构化营养报告入口。响应包含菜品、份量、营养素、
`analysisStatus` 和 `analysisReport`；报告保存总体置信度、结果版本、复核/失败原因及分析时间，
不生成健康建议或来源引用。

completed、failed、review-required 是三种不同结果。`needs_review` 与 `failed` 都允许显式
retry；人工修正数据优先于 AI 数据。无法解析的结果信封进入
`nutrition-analysis-result-dlt`，可解析的非法结果必须落 failed 报告，不能永久停留 analysing。
不可恢复事件立即进入 DLT；数据库等普通异常先按 Spring Kafka 错误处理器有限重试。

capture-context 的 `notes` 只为新工具 Schema 返回。HealthMind 固定 release 发送
`include_meal_notes=true` 时才包含非空备注；旧 v1.0 release 保持原响应形状，避免破坏已冻结的
`additionalProperties:false` 契约。

## 进一步阅读

- [模块 AGENTS.md](../AGENTS.md)：AI 导航（任务 → 读什么、状态机与易错点）。
- [根 AGENTS.md](../../AGENTS.md)：仓库规范、阅读导航与项目背景。
- [integration-contracts/doc/README.md](../../integration-contracts/doc/README.md)：跨服务事件契约。