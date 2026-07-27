# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

HealthServer 是一个基于 Spring Cloud 的微服务健康/饮食管理系统。目前仅实现了 **API 网关** 模块，下游服务（`user-service`、`diet-service`、`health-service`）尚未实现。

## 技术栈

| 组件 | 版本 |
|---|---|
| Kotlin | 2.3.21 |
| Spring Boot | 4.1.0（使用 Jackson 3，包名 `tools.jackson`，不是 `com.fasterxml.jackson`） |
| Spring Cloud | 2025.1.2 |
| Spring Cloud Alibaba | 2025.1.0.0 |
| Java | 21（toolchain） |
| Gradle | 9.6.1（wrapper） |

## 常用命令

```bash
# 构建所有模块
./gradlew build

# 仅构建 gateway
./gradlew :gateway:build

# 启动 gateway
./gradlew :gateway:bootRun

# 运行所有测试
./gradlew test

# 运行单个测试类（例如 RateLimitFilterTest）
./gradlew :gateway:test --tests "cn.esuny.gateway.filter.RateLimitFilterTest"

# 清理
./gradlew clean
```

## 多模块结构

根 `build.gradle` 为所有子模块统一配置：
- `java-library` 和 `io.spring.dependency-management` 插件
- Java 21 toolchain
- Spring Cloud BOM + Spring Cloud Alibaba BOM 统一版本管理
- 公共依赖：`kotlin-reflect`、`jackson-module-kotlin`、`reactor-kotlin-extensions`、`kotlinx-coroutines-reactor`

每个子模块的 `build.gradle` 声明自己的 Kotlin/Spring Boot 插件和模块专属依赖。

## 网关架构

网关（`gateway/`）是唯一的流量入口（端口 8080），采用 **WebMVC** 版本的 Spring Cloud Gateway（Servlet + Tomcat，非 WebFlux）。

### 路由配置（Nacos 服务发现）

在 `GatewayRouteConfig.kt` 中通过代码定义路由规则，使用 `lb://` 负载均衡 URI：
- `/api/user/**` → `user-service`
- `/api/diet/**` → `diet-service`
- `/api/health/**` → `health-service`

路由使用 `lb://` 协议，通过 Nacos 服务发现解析服务实例，支持负载均衡。

### 过滤器链（Servlet Filter，按 precedence 排序）

1. `TraceIdFilter`（最高优先级）— 生成/提取 `X-Trace-Id`，设置 SLF4J MDC
2. `RequestLoggingFilter`（+1）— 记录请求方法、URI、IP、User-Agent、状态码、耗时
3. `RateLimitFilter`（+2）— 基于客户端 IP 的令牌桶限流（20 req/s，突发 40，返回 429）

### 配置管理

#### Nacos 配置中心
- 通过 `spring.config.import=nacos:` 启用，配置文件名为 `GateWay_Application.yaml`
- 支持动态刷新：`RateLimitProperties` 使用 `@RefreshScope`，修改 Nacos 配置后自动生效
- 配置优先级：Nacos 远程配置 > 本地 `application.yaml`

#### 配置分类
- **动态配置**（支持热更新）：限流参数（`gateway.rate-limit.*`）
- **静态配置**（需重启）：CORS、MVC、日志等框架级配置

### 错误处理

- `GlobalExceptionHandler`（`@RestControllerAdvice`）— 捕获 404、405、异常 → 统一 `ApiResponse` JSON
- `FallbackController` — `/fallback` 端点，返回 503 用于熔断降级

### 其他配置

- `CorsConfig` — 硬编码 CORS 规则（不支持动态刷新），允许所有来源（生产环境需限制）
- `JacksonConfig` — Jackson 3：日期不转时间戳、忽略未知属性、时区 GMT+8
- `GatewayHealthIndicator` — 扩展 `/actuator/health`，返回启动时间和运行时长

### 统一响应模型

`ApiResponse<T>` 统一包装所有响应：`code`、`message`、`data`、`traceId`、`timestamp`。

## 关键约定

- 基础包名：`cn.esuny`
- 代码注释使用中文
- `cn.esuny.gateway` 下的包结构：`config/`、`filter/`、`handler/`、`health/`、`model/`
- 新增子模块放在独立目录，有独立 `build.gradle`，并在 `settings.gradle` 中注册

## 外部依赖

- **Nacos** 服务发现和配置中心（地址见 `application.yaml`）
