# Gateway — 模块大体说明

HealthServer 的统一流量入口（默认端口 `8091`），基于 Spring Cloud Gateway WebFlux。负责路由、限流、日志和认证预处理，不承载业务数据。

## 技术栈

| 组件 | 说明 |
|---|---|
| Web | Spring Cloud Gateway WebFlux（响应式，非 Servlet） |
| 认证 | Authentik OIDC/JWKS，RS256 令牌验证 |
| 服务发现 | Nacos，分组 `HEALTH_GROUP` |
| 配置 | Nacos 配置组 `GATEWAY_GROUP` |

外部地址和 OIDC 参数只从环境变量或 Nacos 注入；仓库配置不包含可连接的真实地址。

## 请求处理顺序

| 顺序 | 过滤器 | 作用 |
|---|---|---|
| 1 | CORS | 处理跨域和预检请求 |
| 2 | `TraceIdFilter` | 生成或透传 `X-Trace-Id` |
| 3 | `RequestLoggingFilter` | 记录请求摘要和耗时 |
| 4 | `RateLimitFilter` | 默认 20 req/s、突发 40 的 IP 令牌桶限流 |
| 5 | `AuthentikAuthFilter` | 验证令牌并注入可信身份头 |

认证成功后由 Gateway 写入 `X-Auth-Subject` 等内部身份头，并移除客户端伪造的同名头；后端只信任来自受控 Gateway 的请求。

## 路由

| 路径 | 目标 |
|---|---|
| `/v1/auth/**`、`/v1/files/avatar/**`、`/v1/users/**` | `lb://Orion` |
| `/v1/nutri/**` | `lb://NutriMemo` |

每条路由附加 `X-Gateway-Source: HealthServer-Gateway`。`/v1/auth/**` 在 Gateway 配置中存在，但 Orion 当前 OpenAPI 未列出对应认证接口，归属仍待确认。

## 代码位置

- `config/`：过滤器顺序、Nacos、CORS、限流和认证配置。
- `filter/`：请求级 WebFilter。
- `handler/`、`health/`：`/fallback` 兜底端点（免认证白名单内）与自定义健康指示器。
- `GatewayApplication.kt`：应用入口。
- `src/main/resources/application.yaml`：无密钥的本地配置骨架。

网关自身端点只有 `/fallback` 与 Actuator `health,info`；不承载业务数据，也不直连数据库或 Kafka。

## 验证

```bash
./gradlew :gateway:test
./gradlew :gateway:bootRun
```

`bootRun` 需要可用的 Nacos、Authentik 配置以及后端服务发现实例。

## 进一步阅读

- [模块 AGENTS.md](../AGENTS.md)：AI 导航（任务 → 读什么、关键事实与易错点）。
- [根 AGENTS.md](../AGENTS.md)：仓库规范、路由表与阅读导航。