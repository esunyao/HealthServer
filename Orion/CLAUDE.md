# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Orion 是 HealthServer 微服务架构中的 **用户管理服务**（端口 8081），负责用户注册、登录、Token 管理和用户画像维护。采用 Spring Boot WebMVC（Servlet）+ MyBatis-Plus + PostgreSQL + Redis 架构。

## 技术栈

| 组件 | 版本/说明 |
|---|---|
| Spring Boot | 4.1.0（WebMVC，Servlet 模式，非 WebFlux） |
| MyBatis-Plus | 3.5.17（`mybatis-plus-spring-boot4-starter`） |
| PostgreSQL | `User` schema，多 Schema 设计 |
| Redis | Spring Data Redis 4.x，存储 Refresh Token |
| JWT | jjwt 0.12.6，双 Token 机制（Access 15min + Refresh 7d） |
| 密码加密 | Spring Security Crypto（BCrypt） |
| Jackson | 3.x（`tools.jackson`，Spring Boot 4 默认） |

## 常用命令

```bash
# 构建
./gradlew :orion:build

# 启动（需要 PostgreSQL 和 Redis 服务）
./gradlew :orion:bootRun

# 测试
./gradlew :orion:test

# 运行单个测试类
./gradlew :orion:test --tests "cn.esuny.orion.SomeTest"
```

## 架构

Orion 遵循经典三层架构：

```
Controller (REST API)
    ↓
Service (业务逻辑)
    ↓
Mapper (MyBatis-Plus 数据访问)
    ↓
PostgreSQL (User schema)
```

### 认证流程

1. **注册** → BCrypt 加密密码 → 插入 users + user_profiles 表
2. **登录** → 验证密码 → 生成 JWT（Access + Refresh Token）→ Refresh Token 存入 Redis
3. **刷新** → 校验 Refresh Token → 从 Redis 比对 → 生成新的 Token 对
4. **登出** → 从 Redis 删除 Refresh Token

### 用户信息获取

Controller 通过 `@RequestHeader("X-User-Id")` 获取当前用户 ID（由 Gateway 认证后注入）。

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/v1/auth/register` | 用户注册 |
| POST | `/v1/auth/login` | 用户登录，返回 Token |
| POST | `/v1/auth/refresh` | 刷新 Token |
| POST | `/v1/auth/logout` | 用户登出 |
| GET | `/v1/users/self` | 获取当前用户信息 |
| PUT | `/v1/users/self` | 更新当前用户信息 |
| PUT | `/v1/users/self/password` | 修改密码 |
| GET | `/v1/users/self/profile` | 获取用户画像 |
| PUT | `/v1/users/self/profile` | 更新用户画像 |

## 包结构

```
cn.esuny.orion/
├── config/                 # 配置类
│   ├── MyBatisPlusConfig   # MyBatis-Plus 分页插件 + TypeHandler 注册
│   ├── RedisConfig         # Redis 连接配置
│   └── JacksonConfig       # Jackson 3 序列化配置
├── controller/rest/        # REST 控制器
│   ├── AuthController      # 认证端点（/v1/auth/**）
│   └── UserController      # 用户端点（/v1/users/**）
├── handler/                # 异常处理
│   ├── BusinessException   # 业务异常
│   └── GlobalExceptionHandler  # 全局异常处理器
├── mapper/                 # MyBatis-Plus Mapper
│   ├── UserMapper          # users 表访问
│   └── UserProfileMapper   # user_profiles 表访问
├── model/
│   ├── dto/auth/           # 认证相关请求 DTO
│   ├── dto/user/           # 用户信息请求 DTO
│   ├── entity/user/        # 实体（User、UserProfile）
│   ├── enums/user/         # 枚举（UserStatus、Gender、ActivityLevel、HealthGoal）
│   ├── result/             # ApiResponse 统一响应
│   ├── typehandler/        # PostgreSQL 特殊类型处理器
│   └── vo/user/            # 视图对象（UserVO、UserProfileVO）
├── service/
│   ├── AuthService         # 认证业务接口
│   ├── UserService         # 用户业务接口
│   └── impl/               # 业务实现
└── util/
    └── JwtUtil             # JWT 生成/解析
```

## 数据库设计（PostgreSQL）

### Schema: `User`

**users 表**
- `user_id` (BigSerial, PK) — 用户唯一标识
- `username` (Unique) — 登录用户名
- `email` (Unique) — 邮箱地址
- `password_hash` — bcrypt 密码哈希
- `nickname` — 昵称
- `avatar_url` — 头像链接
- `status` — active / disabled / deleted
- `last_login_at` — 最后登录时间
- `created_at`, `updated_at` — 时间戳

**user_profiles 表**
- `profile_id` (BigSerial, PK) — 画像记录 ID
- `user_id` (FK → users) — 1:1 关系，级联删除
- `age`, `gender`, `height_cm`, `weight_kg`, `bmi` — 身体数据
- `activity_level`, `health_goal` — 活动水平和健康目标
- `allergies`, `dietary_restrictions`, `medical_conditions`, `preferred_cuisine` — PostgreSQL TEXT[] 数组
- `daily_water_ml` — 每日饮水目标

## 关键实现细节

### UUID 处理

数据库使用 BigSerial 主键（Long），但部分字段在概念上是 UUID。MyBatis-Plus 通过 `UuidTypeHandler` 处理类型转换（已注册在 `MyBatisPlusConfig`）。

### PostgreSQL TEXT[] 数组

`PgStringArrayTypeHandler` 处理 PostgreSQL 的 TEXT[] 类型，在 Kotlin List<String> 和数据库数组之间转换。

### Redis 配置

使用 `GenericJacksonJsonRedisSerializer`（Spring Boot 4 废弃了旧版 `Jackson2JsonRedisSerializer`），通过 Jackson 3 的 `ObjectMapper` 进行序列化。

### JWT 双 Token

- Access Token: 15 分钟，用于 API 认证
- Refresh Token: 7 天，存储在 Redis 中，用于获取新的 Access Token
- JWT payload 使用 `tokenType` 区分 `access` 和 `refresh`；Gateway 仅接受 `access`，刷新/登出仅接受 `refresh`
- 密钥和有效期配置在 `application.yaml` 的 `jwt.*` 属性

## 外部依赖

- **PostgreSQL** — `192.168.3.101:5432/Health`（User schema）
- **Redis** — `192.168.3.101:6379`
- **Nacos** — `192.168.3.101:8848`（配置组：ORION_GROUP）
