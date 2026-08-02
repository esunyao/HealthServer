# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Gateway 是 HealthServer 微服务架构的 **API 网关**（端口 8080），采用 Spring Cloud Gateway WebFlux 作为流量入口。负责路由分发、限流、日志和认证预处理。

## 技术栈

| 组件 | 版本/说明 |
|---|---|
| Spring Cloud Gateway | WebFlux 版本（`spring-cloud-starter-gateway-server-webflux`） |
| Spring Boot | 4.1.0（WebFlux，响应式，非 Servlet） |
| Jackson | 3.x（`tools.jackson`，Spring Boot 4 默认） |
| JJWT | 0.12.6（JWT 验证） |
| Redis | Spring Data Redis Reactive（Token 黑名单检查） |

## 常用命令

```bash
# 构建
./gradlew :gateway:build

# 启动
./gradlew :gateway:bootRun

# 测试
./gradlew :gateway:test

# 运行单个测试类
./gradlew :gateway:test --tests "cn.esuny.gateway.filter.RateLimitFilterTest"
```

## 架构

Gateway 采用过滤器链模式处理请求：

```
Client Request
    ↓
TraceIdFilter (生成/提取 X-Trace-Id)
    ↓
RequestLoggingFilter (记录请求日志)
    ↓
RateLimitFilter (基于 IP 的令牌桶限流)
    ↓
JwtAuthFilter (JWT 认证 + 注入 X-User-Id)   ← 新增
    ↓
路由匹配 → lb://Orion → 负载均衡 → 后端服务
    ↓
响应返回
```

## 路由配置

在 `application.yaml` 中通过 Spring Cloud Gateway WebFlux 配置路由规则：

| 路径模式 | 目标服务 | 说明 |
|---|---|---|
| `/v1/auth/**` | `lb://Orion` | 认证端点（注册/登录/刷新/登出） |
| `/v1/users/**` | `lb://Orion` | 用户管理端点（查询/修改信息） |
| `/v1/diet/**` | `lb://DietServer` | 饮食管理端点（规划中） |

路由使用 `lb://` 协议，通过 Nacos 服务发现解析服务实例地址。

### 路由 Filter

每个路由添加自定义请求头：`X-Gateway-Source: HealthServer-Gateway`

## 过滤器链（按 Precedence 排序）

1. **TraceIdFilter**（最高优先级）
   - 生成或提取 `X-Trace-Id` 请求头
   - 设置 SLF4J MDC 以便日志追踪

2. **RequestLoggingFilter**（+1）
   - 记录请求方法、URI、IP、User-Agent、状态码、耗时

3. **RateLimitFilter**（+2）
   - 基于客户端 IP 的令牌桶限流
   - 默认：20 请求/秒，突发容量 40
   - 返回 429 Too Many Requests

4. **JwtAuthFilter**（+3）← **新增**
   - JWT 认证过滤器，验证 Token 有效性
   - 白名单路径（`/v1/auth/**`、`/actuator/**`、`/fallback`）无需认证
   - 从 Token 解析 userId，注入到 `X-User-Id` header
   - 检查 Redis 黑名单，已登出的 Token 被拒绝
   - 返回 401 Unauthorized 如果 Token 无效/过期/已登出

## 包结构

```
cn.esuny.gateway/
├── config/
│   ├── CorsConfig            # CORS 配置（允许所有来源，生产环境需限制）
│   ├── JacksonConfig         # Jackson 3 配置（日期格式、时区 GMT+8）
│   ├── JwtProperties         # JWT 密钥配置
│   └── RateLimitProperties   # 限流参数（支持 @RefreshScope 热更新）
├── filter/
│   ├── TraceIdFilter         # 链路追踪 ID 过滤器
│   ├── RequestLoggingFilter  # 请求日志过滤器
│   ├── RateLimitFilter       # 限流过滤器
│   └── JwtAuthFilter         # JWT 认证过滤器（新增）
├── handler/
│   ├── GlobalExceptionHandler  # 全局异常处理 → 统一 ApiResponse JSON
│   └── FallbackController    # 降级端点（/fallback → 503）
├── health/
│   └── GatewayHealthIndicator  # 健康检查扩展（启动时间、运行时长）
├── model/
│   └── ApiResponse           # 统一响应模型
└── security/
    └── JwtUtil               # JWT 验证工具类（新增）
```

## 配置管理

### Nacos 配置中心

- 配置文件名：`GateWay_Application.yaml`
- 配置组：`GATEWAY_GROUP`
- 支持动态刷新：`RateLimitProperties` 使用 `@RefreshScope`
- 配置优先级：Nacos 远程配置 > 本地 `application.yaml`

### 配置分类

- **动态配置**（支持热更新）：限流参数（`gateway.rate-limit.*`）
- **静态配置**（需重启）：CORS、日志等框架级配置

## 错误处理

- `GlobalExceptionHandler`（`@RestControllerAdvice`）— 捕获异常 → 统一 `ApiResponse` JSON
- `FallbackController` — `/fallback` 端点，返回 503 用于熔断降级

## 其他配置

- `CorsConfig` — CORS 配置（硬编码，不支持动态刷新）
- `JacksonConfig` — Jackson 3 序列化配置
- `GatewayHealthIndicator` — 扩展 `/actuator/health`，返回启动时间和运行时长

## 外部依赖

- **Nacos** — `192.168.3.101:8848`（配置组：GATEWAY_GROUP）
- **Redis** — `192.168.3.101:6379`（与 Orion 相同实例，用于 Token 黑名单检查）
