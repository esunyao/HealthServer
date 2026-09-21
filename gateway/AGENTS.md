# gateway — AI 工作指南（导航）

> 本文件只做导航与理解，不新增规范；规范来源是根 [`AGENTS.md`](../AGENTS.md) 与 [`doc/README.md`](./doc/README.md)。行为、接口、配置与安全结论以源码、`application.yaml`、契约与测试为准。

## 这个模块是什么

HealthServer 的统一流量入口（默认端口 `8091`），基于 Spring Cloud Gateway **WebFlux（响应式，不是 Servlet）**。负责路由、限流、日志与认证预处理，**不承载业务数据、不访问数据库、不接 Kafka**。

边界：
- owns：对外路由、CORS、限流、`X-Trace-Id`、请求日志、OIDC 令牌验证与可信身份头注入、`/fallback`。
- not owns：任何业务逻辑与数据（属于 Orion / NutriMemo / HealthMind）；对后端服务的直接调用（只做转发）。

## 快速事实

| 项 | 值 |
|---|---|
| Gradle | `:gateway`（应用名 `GateWay`，大小写特殊，`src/main/resources/application.yaml`） |
| 入口 | [`GatewayApplication.kt`](./src/main/kotlin/cn/esuny/gateway/GatewayApplication.kt) |
| 端口 | `${SERVER_PORT:8091}` |
| 技术栈 | Spring Cloud Gateway WebFlux + `spring-security-oauth2-jose`（刻意不引入 `starter-security`，见 [`build.gradle`](./build.gradle)） |
| 配置来源 | 仅 [`application.yaml`](./src/main/resources/application.yaml)；Nacos 导入 `GateWay_Application.yaml?group=GATEWAY_GROUP`（**非 optional，无 Nacos 无法启动**）；discovery 分组 `HEALTH_GROUP` |
| 必需环境变量 | `NACOS_SERVER_ADDR/USERNAME/PASSWORD`、`AUTHENTIK_ISSUER_URI`、`AUTHENTIK_AUDIENCES`（见 application.yaml 头部速查表） |
| 自身端点 | `/fallback`（在 OIDC 白名单）、Actuator `health,info` |
| 数据库/迁移 | 无（无 `db/migration`） |

## 代码地图

| 位置 | 职责 |
|---|---|
| [`config/FilterOrder.kt`](./src/main/kotlin/cn/esuny/gateway/config/FilterOrder.kt) | **过滤器顺序的唯一集中登记处**；调整顺序只改这里 |
| [`filter/`](./src/main/kotlin/cn/esuny/gateway/filter/) | `TraceIdFilter`、`RequestLoggingFilter`、`RateLimitFilter`、`AuthentikAuthFilter` |
| [`config/`](./src/main/kotlin/cn/esuny/gateway/config/) | `AuthentikJwtDecoderConfig`/`AuthentikProperties`（OIDC）、`CorsConfig`/`CorsProperties`（CORS）、`OidcAuthProperties`（白名单）、`RateLimitProperties`、`JacksonConfig` |
| [`security/AudienceValidator.kt`](./src/main/kotlin/cn/esuny/gateway/security/AudienceValidator.kt) | JWT audience 校验 |
| [`handler/`](./src/main/kotlin/cn/esuny/gateway/handler/) | `FallbackController`（`/fallback`）、`GlobalExceptionHandler` |
| [`health/GatewayHealthIndicator.kt`](./src/main/kotlin/cn/esuny/gateway/health/GatewayHealthIndicator.kt) | 自定义健康指示器 |

注：模块根的 `gateway/config/` 是空目录，真实配置在 `src/main/resources/application.yaml`。

## 任务 → 读什么

| 你要做的事 | 先读 |
|---|---|
| 改路由规则 | [`application.yaml`](./src/main/resources/application.yaml)（`spring.cloud.gateway.server.webflux.routes`）→ 根 [`AGENTS.md`](../AGENTS.md) 路由表 |
| 改过滤器顺序 | [`config/FilterOrder.kt`](./src/main/kotlin/cn/esuny/gateway/config/FilterOrder.kt) |
| 改限流阈值/算法 | [`filter/RateLimitFilter.kt`](./src/main/kotlin/cn/esuny/gateway/filter/RateLimitFilter.kt) + `application.yaml` 的 `gateway.rate-limit` |
| 改认证/白名单/身份头 | [`filter/AuthentikAuthFilter.kt`](./src/main/kotlin/cn/esuny/gateway/filter/AuthentikAuthFilter.kt)、[`config/OidcAuthProperties.kt`](./src/main/kotlin/cn/esuny/gateway/config/OidcAuthProperties.kt) |
| 改 CORS | [`config/CorsConfig.kt`](./src/main/kotlin/cn/esuny/gateway/config/CorsConfig.kt) + `application.yaml` 的 `gateway.cors` |
| 排查请求链路 | `X-Trace-Id` 透传（[`filter/TraceIdFilter.kt`](./src/main/kotlin/cn/esuny/gateway/filter/TraceIdFilter.kt)）→ 后端模块 `AGENTS.md` |

## 关键事实与易错点

- **响应式边界**：本模块是 WebFlux 响应式代码，写过滤器/处理器时不要引入阻塞调用或 Servlet API；根 `AGENTS.md` 要求保留这个边界。
- **请求处理顺序**（改顺序会改变安全语义）：CORS → `TraceIdFilter` → `RequestLoggingFilter` → `RateLimitFilter`（默认 20 req/s、burst 40）→ `AuthentikAuthFilter`（顺序常量见 `config/FilterOrder.kt`）。
- **身份头信任模型**：`AuthentikAuthFilter` 验证令牌后注入 `X-Auth-Subject`/`X-Auth-Username`/`X-Auth-Email`/`X-Auth-Display-Name`/`X-Auth-Email-Verified`，并**移除客户端伪造的同名头**；后端（Orion/NutriMemo）只信任来自受控 Gateway 的请求。
- **白名单**：`/actuator/`、`/fallback` 免认证，且支持 Nacos 动态刷新（`refreshEnabled=true`）。
- **Nacos 非 optional**：`nacos:GateWay_Application.yaml` 导入没有 `optional:` 前缀，缺少 Nacos 时网关起不来；这是有意设计，防止静默使用弱配置。
- 每条路由附加 `X-Gateway-Source: HealthServer-Gateway`；后端据此识别流量来源。
- `/v1/auth/**` 路由在网关配置中存在，但 Orion 当前 OpenAPI 没有对应接口——归属仍待确认，**不要擅自删除或重命名该路由**。

## 接口与契约

- 无 `openapi.yaml`（非业务 API 服务）。
- 对外路由见根 [`AGENTS.md`](../AGENTS.md) 的「路由」表；路由目标经 Nacos 以 `lb://` 解析。

## 测试与验证

```bash
./gradlew :gateway:test
./gradlew :gateway:bootRun   # 需要可用 Nacos、Authentik 与后端发现实例
```

- 测试仅 [`AuthentikAuthFilterTest.kt`](./src/test/kotlin/cn/esuny/gateway/filter/AuthentikAuthFilterTest.kt)；`filter/`、`security/` 测试目录存在但为空。
- 改动认证、过滤器顺序或路由时补回归测试。

## 相关文档

- [doc/README.md](./doc/README.md) — 模块公开大体说明（过滤器/路由/代码位置）。
- [../AGENTS.md](../AGENTS.md) — 仓库规范、路由表、项目背景与阅读导航。
- 后端侧：[../Orion/AGENTS.md](../Orion/AGENTS.md)、[../NutriMemo/AGENTS.md](../NutriMemo/AGENTS.md)。
- `docp/`（若维护者提供）为私有详细说明，只读参考、不写入；`doc-project/` 为私有项目背景，见根 `AGENTS.md`。
