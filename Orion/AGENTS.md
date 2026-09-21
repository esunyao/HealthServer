# Orion — AI 工作指南（导航）

> 本文件只做导航与理解，不新增规范；规范来源是根 [`AGENTS.md`](../AGENTS.md) 与 [`doc/README.md`](./doc/README.md)。行为、接口、配置与安全结论以源码、[`openapi.yaml`](./openapi.yaml)、配置与测试为准。

## 这个模块是什么

**用户画像系统**：用户身份、画像、健康记录和头像文件服务（默认端口 `8090`）。Spring WebMVC **Servlet** 服务（非响应式），用户请求通常经 Gateway 进入。

项目背景定位（不可变动）：Orion 为各 App 提供全方位的用户基础画像（年龄、体重等），是 HealthMind AI 链路中「最小营养健康上下文」的数据来源。

边界：
- owns：用户身份与资料、身体测量、健康目标、过敏、疾病、饮食限制、烹饪偏好、临床观察、同意记录；头像文件直传与清理；`/internal/v1/ai-context/nutrition` 内部营养上下文。
- not owns：AI 分析与任务（HealthMind）、餐食与营养摄入（NutriMemo）、认证服务器的令牌签发（Authentik）。

## 快速事实

| 项 | 值 |
|---|---|
| Gradle | `:orion`（目录名 `Orion`） |
| 入口 | [`OrionApplication.kt`](./src/main/kotlin/cn/esuny/orion/OrionApplication.kt) |
| 端口 | `${SERVER_PORT:8090}` |
| 技术栈 | WebMVC + Spring Security Resource Server + MyBatis-Plus 3.5.17 + PostgreSQL（`orion` schema）+ AWS S3 SDK 2.31.6（S3 兼容：RustFS/MinIO/OSS） |
| 配置来源 | [`application.yaml`](./src/main/resources/application.yaml)；Nacos `Orion_Application.yaml`（group 默认 `ORION_GROUP`）；discovery 分组 `HEALTH_GROUP` |
| 迁移 | [`db/migration/V1__create_orion_user_service.sql`](./src/main/resources/db/migration/V1__create_orion_user_service.sql)（`spring.flyway.enabled=false`，由 [`config/FlywayConfig.kt`](./src/main/kotlin/cn/esuny/orion/config/FlywayConfig.kt) 以 `schemas("orion")` 手动装配） |
| 契约 | [`openapi.yaml`](./openapi.yaml)（OpenAPI 3.0.3，「Orion 用户服务 API」v1.0.0） |
| 无 Kafka | 本模块不接 Kafka（确认于 [`build.gradle`](./build.gradle)） |

## 代码地图

| 位置 | 职责 |
|---|---|
| [`controller/rest/`](./src/main/kotlin/cn/esuny/orion/controller/rest/) | `UserController`（资料/测量/目标/过敏/疾病/限制/偏好/观察/同意）、`HealthRecordController`、`FileController`（头像） |
| [`identity/`](./src/main/kotlin/cn/esuny/orion/identity/) | `@CurrentUser` 注解 + `CurrentUserArgumentResolver`：把 Gateway 注入的 `X-Auth-Subject` 解析为 `AuthenticatedUser` |
| [`internal/nutrition/`](./src/main/kotlin/cn/esuny/orion/internal/nutrition/) | 供 HealthMind 使用的营养上下文查询与**独立 M2M 安全链**（`OrionInternalSecurityConfig`） |
| [`service/impl/`](./src/main/kotlin/cn/esuny/orion/service/impl/) | `UserServiceImpl`、`HealthRecordServiceImpl`、`FileServiceImpl`、`AvatarOrphanReconciler`（孤儿头像对账）、`FileCleanupTaskServiceImpl` |
| [`mapper/`](./src/main/kotlin/cn/esuny/orion/mapper/) | MyBatis-Plus 映射（`UserMapper`、`UserProfileMapper`、`HealthRecordMappers`、`FileCleanupTaskMapper`） |
| [`model/`](./src/main/kotlin/cn/esuny/orion/model/) | `dto/`、`entity/`、`enums/`、`vo/`、`result/ApiResponse`、`typehandler/`（`PgJsonbTypeHandler`、`PgUuidTypeHandler`） |
| [`config/`](./src/main/kotlin/cn/esuny/orion/config/) | Flyway、MyBatis-Plus、OSS、WebMvc、清理调度（`CleanupSchedulingConfig`） |
| [`service/SnowflakeIdGenerator.kt`](./src/main/kotlin/cn/esuny/orion/service/SnowflakeIdGenerator.kt) | 雪花 ID 生成（与 NutriMemo 同款方案） |

注：`util/` 目录存在但没有 Kotlin 源文件。

## 任务 → 读什么

| 你要做的事 | 先读 |
|---|---|
| 加/改用户资料字段 | [`controller/rest/UserController.kt`](./src/main/kotlin/cn/esuny/orion/controller/rest/UserController.kt) → [`service/impl/UserServiceImpl.kt`](./src/main/kotlin/cn/esuny/orion/service/impl/UserServiceImpl.kt) → [`mapper/UserProfileMapper.kt`](./src/main/kotlin/cn/esuny/orion/mapper/UserProfileMapper.kt) → 迁移 SQL → [`openapi.yaml`](./openapi.yaml) |
| 改头像上传流程 | [`controller/rest/FileController.kt`](./src/main/kotlin/cn/esuny/orion/controller/rest/FileController.kt) → [`service/impl/FileServiceImpl.kt`](./src/main/kotlin/cn/esuny/orion/service/impl/FileServiceImpl.kt) → [`config/OssProperties.kt`](./src/main/kotlin/cn/esuny/orion/config/OssProperties.kt) |
| 改头像清理/对账 | [`service/impl/AvatarOrphanReconciler.kt`](./src/main/kotlin/cn/esuny/orion/service/impl/AvatarOrphanReconciler.kt) + `application.yaml` 的 `orion.oss.cleanup` |
| 改内部营养上下文（AI 链路） | [`internal/nutrition/`](./src/main/kotlin/cn/esuny/orion/internal/nutrition/) → [`OrionInternalSecurityConfig.kt`](./src/main/kotlin/cn/esuny/orion/internal/nutrition/OrionInternalSecurityConfig.kt) → 根 `doc-project/0920HealthMindOrionMCP返回结构说明.md`（私有背景） |
| 改身份解析 | [`identity/CurrentUserArgumentResolver.kt`](./src/main/kotlin/cn/esuny/orion/identity/CurrentUserArgumentResolver.kt) |
| 排查鉴权问题 | 根 [`AGENTS.md`](../AGENTS.md)（Gateway 头模型）→ `identity/` + `application.yaml` 的 `orion.internal.security.*` |

## 关键事实与易错点

- **身份边界**：用户侧认证由 Gateway 完成；Orion 用 `@CurrentUser` 把可信头解析为主体，控制器一律按当前用户主体查询数据，不接受请求体携带的用户 ID。
- **内部接口独立安全链**：`securityMatcher("/internal/**")`，要求 `SCOPE_orion.ai-context.read` 并校验 JWT 的 `azp`/`client_id`（默认允许 `healthmind-orion`；audience 默认 `orion-internal`）——与用户链路互不共用过滤器链。
- **Flyway 手动装配**：`spring.flyway.enabled=false`，schema 由 `FlywayConfig` 显式指定为 `orion`；新增迁移文件放 `db/migration`，本地不会自动执行（需要相应环境）。
- **头像直传三步**：presign（`avatar-staging/{userId}/...` 短时地址，5 分钟、最大 5MB、jpeg/png/webp/gif）→ confirm（校验对象存在、归属与 staging 前缀）→ 服务端转入 `avatars/{userId}/...` 并更新头像记录。
- **清理调度是常驻能力**：`FileCleanupTaskServiceImpl`（fixed-delay 60s）+ `AvatarOrphanReconciler`（孤儿扫描 cron `0 30 3 * * *`、保护期 24h、最大重试 8 次）；改动文件存储时要考虑这两个任务。
- **接口语义差异**：`cuisine-preferences` 是 `PUT` **整体替换**（不是增量补丁）；`clinical-observations` 与 `consents` 只增不改（GET/POST）。
- 表结构见迁移 SQL；JSONB 与 UUID 字段依赖 `PgJsonbTypeHandler`/`PgUuidTypeHandler`，手写 SQL 时注意类型转换。

## 接口与契约

- 用户接口：`/v1/users/self/**`（资料、测量、目标、过敏、疾病、饮食限制、烹饪偏好、临床观察、同意）与 `/v1/files/avatar/*`；字段契约以 [`openapi.yaml`](./openapi.yaml) 为准。
- 内部接口：`/internal/v1/ai-context/nutrition`（POST，M2M，返回最小营养健康上下文；字段说明见私有 `doc-project/0920HealthMindOrionMCP返回结构说明.md`）。
- 调用方：HealthMind 经 MCP 工具 `orion.nutrition_context.get` 间接读取（见 [../HealthMind/AGENTS.md](../HealthMind/AGENTS.md)）。

## 测试与验证

```bash
./gradlew :orion:test
./gradlew :orion:bootRun   # 需要 PostgreSQL、Nacos、Authentik 与 S3 兼容对象存储
```

- 测试在 [`src/test/kotlin/cn/esuny/orion/`](./src/test/kotlin/cn/esuny/orion/)：配置/迁移脚本、异常处理、内部营养上下文服务、文件与身份服务；`controller/rest/` 测试目录暂空。
- 测试配置禁用 Nacos/Flyway/调度；[`src/test/resources/application.yaml`](./src/test/resources/application.yaml) 含遗留 `jwt.*` 测试密钥配置，**不要扩散或复用**。

## 相关文档

- [doc/README.md](./doc/README.md) — 模块公开大体说明。
- [../AGENTS.md](../AGENTS.md) — 仓库规范、阅读导航与项目背景。
- [../HealthMind/AGENTS.md](../HealthMind/AGENTS.md) — 营养上下文的消费方。
- 私有：`doc-project/`（项目背景，不提交）；`docp/`（若存在，只读参考、不写入）。
