# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

HealthServer 是一个基于 Spring Cloud 的微服务健康/饮食管理系统。采用多模块 Gradle 项目结构，目前仅实现了 **API 网关** 模块，下游服务尚未实现。

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
├── settings.gradle                 # 模块注册
├── CLAUDE.md                       # 本文件（项目级指引）
│
├── gateway/                        # API 网关模块（唯一实现）
│   ├── CLAUDE.md                   # 网关模块详细指引
│   ├── build.gradle                # 网关模块构建配置
│   └── src/
│       ├── main/
│       │   ├── kotlin/cn/esuny/gateway/
│       │   │   ├── config/         # 配置类（CORS、Jackson、路由、限流属性）
│       │   │   ├── filter/         # Servlet 过滤器链（TraceId、日志、限流）
│       │   │   ├── handler/        # 异常处理、降级控制器
│       │   │   ├── health/         # 健康检查扩展
│       │   │   └── model/          # 统一响应模型 ApiResponse
│       │   └── resources/
│       │       └── application.yaml
│       └── test/
│
├── user-service/                   # 用户服务（未实现）
├── diet-service/                   # 饮食服务（未实现）
└── health-service/                 # 健康服务（未实现）
```

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

## 关键约定

- 基础包名：`cn.esuny`
- 代码注释使用中文
- 新增子模块放在独立目录，有独立 `build.gradle`，并在 `settings.gradle` 中注册
- 网关模块的详细架构说明见 `gateway/CLAUDE.md`

## 外部依赖

- **Nacos** 服务发现和配置中心（地址见各模块的 `application.yaml`）
