# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

HealthServer 是一个基于 Spring Cloud 的微服务健康/饮食管理系统。采用多模块 Gradle 项目结构，已实现 **API 网关** 和 **Orion 用户管理** 两个模块，其他业务服务尚未实现。

## 技术栈

| 组件 | 版本 |
|---|---|
| Kotlin | 2.3.21 |
| Spring Boot | 4.1.0 |
| Spring Cloud | 2025.1.2 |
| Spring Cloud Alibaba | 2025.1.0.0 |
| Java | 21（toolchain） |
| Gradle | 9.6.1（wrapper） |

## 项目结构

```
HealthServer/
├── build.gradle                    # 根构建文件（统一依赖版本管理）
├── settings.gradle                 # 模块注册：gateway、orion
├── CLAUDE.md                       # 本文件（项目级指引）
│
├── gateway/                        # API 网关模块（端口 8080）
│   ├── CLAUDE.md                   # 网关模块详细指引
│   ├── build.gradle
│   └── src/main/kotlin/cn/esuny/gateway/
│       ├── config/                 # CORS、Jackson、限流属性
│       ├── filter/                 # 过滤器链（TraceId、日志、限流）
│       ├── handler/                # 异常处理、降级控制器
│       ├── health/                 # 健康检查扩展
│       └── model/                  # 统一响应模型 ApiResponse
│
├── Orion/                          # 用户管理服务（端口 8081）
│   ├── CLAUDE.md                   # Orion 模块详细指引
│   ├── build.gradle
│   └── src/main/kotlin/cn/esuny/orion/
│       ├── config/                 # MyBatis-Plus、Redis、Jackson 配置
│       ├── controller/rest/        # REST 控制器（Auth、User）
│       ├── handler/                # 业务异常处理器
│       ├── mapper/                 # MyBatis-Plus Mapper 接口
│       ├── model/                  # 实体、DTO、VO、枚举、TypeHandler
│       ├── service/                # 业务接口与实现
│       └── util/                   # JWT 工具
│
├── DietServer/                     # 饮食管理服务（端口 8082，待实现）
│   ├── CLAUDE.md                   # DietServer 模块详细指引
│   ├── build.gradle
│   └── src/main/kotlin/cn/esuny/dietserver/
│       └── DietServerApplication.kt  # Spring Boot 启动类（基础骨架）
│
└── health-service/                 # 健康服务（未实现）
```

## 常用命令

```bash
# 设置 Java 21 环境（必须，Gradle toolchain 需要）
export JAVA_HOME="D:/Users/Esuny/.jdks/azul-21.0.4"

# 构建所有模块
./gradlew build

# 构建单个模块
./gradlew :gateway:build
./gradlew :orion:build

# 启动服务
./gradlew :gateway:bootRun
./gradlew :orion:bootRun

# 运行测试
./gradlew test
./gradlew :orion:test
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

## Gateway → 后端服务路由

Gateway（WebFlux）路由到后端服务，使用 `lb://` 负载均衡协议：

| 路径模式 | 目标服务 | 说明 |
|---|---|---|
| `/v1/auth/**` | `lb://Orion` | 认证端点（注册/登录/刷新/登出） |
| `/v1/users/**` | `lb://Orion` | 用户管理端点（查询/修改信息） |
| `/v1/diet/**` | `lb://DietServer` | 饮食管理端点（规划中） |

注意：Gateway、Orion 和 DietServer 都使用 Jackson 3（`tools.jackson`），不是 Jackson 2（`com.fasterxml.jackson`）。

## 关键约定

- 基础包名：`cn.esuny`
- 代码注释使用中文
- 新增子模块放在独立目录，有独立 `build.gradle`，在 `settings.gradle` 中注册
- PostgreSQL 使用多 Schema 设计（如 `User` schema），通过 `currentSchema` 连接参数指定默认 schema
- 各模块详细架构说明见各自的 `CLAUDE.md`

## 外部依赖

- **Nacos** 服务发现和配置中心（地址见各模块 `application.yaml`）
- **PostgreSQL** 数据库（Orion 使用，schema 为 `User`）
- **Redis** 缓存/会话存储（Orion 使用，存储 Refresh Token）
