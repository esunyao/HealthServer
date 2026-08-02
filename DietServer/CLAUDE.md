# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

DietServer 是 HealthServer 微服务架构中的 **饮食管理服务**（端口 8082），负责用户饮食记录、营养摄入分析、食物数据库管理等功能。当前处于基础骨架阶段，尚未实现业务功能。

## 技术栈

| 组件 | 版本/说明 |
|---|---|
| Spring Boot | 4.1.0（WebMVC，Servlet 模式） |
| Kotlin | 2.3.21 |
| Java | 21（toolchain） |
| PostgreSQL | 数据库（待配置） |
| Jackson | 3.x（`tools.jackson`，Spring Boot 4 默认） |

## 常用命令

```bash
# 构建
./gradlew :diet-server:build

# 启动（需要 PostgreSQL 服务）
./gradlew :diet-server:bootRun

# 测试
./gradlew :diet-server:test

# 运行单个测试类
./gradlew :diet-server:test --tests "cn.esuny.dietserver.SomeTest"
```

**注意：** 当前模块尚未在 `settings.gradle` 中注册，需要手动添加后才能使用上述命令。

## 架构（规划中）

DietServer 将遵循经典三层架构：

```
Controller (REST API)
    ↓
Service (业务逻辑)
    ↓
Mapper (MyBatis-Plus 数据访问)
    ↓
PostgreSQL (Diet schema)
```

### 规划中的功能模块

1. **食物数据库管理**
   - 食物信息（名称、分类、营养成分）
   - 食物搜索和查询

2. **饮食记录**
   - 用户每餐饮食记录
   - 食物摄入量和时间记录

3. **营养分析**
   - 每日营养摄入统计
   - 营养目标达成情况

4. **饮食计划**
   - 个性化饮食建议
   - 饮食目标设定

## 包结构（规划中）

```
cn.esuny.dietserver/
├── config/                 # 配置类
│   ├── MyBatisPlusConfig   # MyBatis-Plus 分页插件 + TypeHandler 注册
│   ├── RedisConfig         # Redis 连接配置（如需要）
│   └── JacksonConfig       # Jackson 3 序列化配置
├── controller/             # REST 控制器
│   ├── FoodController      # 食物管理端点
│   ├── DietRecordController # 饮食记录端点
│   └── NutritionController  # 营养分析端点
├── handler/                # 异常处理
│   ├── BusinessException   # 业务异常
│   └── GlobalExceptionHandler  # 全局异常处理器
├── mapper/                 # MyBatis-Plus Mapper
│   ├── FoodMapper          # 食物表访问
│   └── DietRecordMapper    # 饮食记录表访问
├── model/
│   ├── dto/                # 请求 DTO
│   ├── entity/             # 实体类
│   ├── enums/              # 枚举类型
│   ├── result/             # ApiResponse 统一响应
│   └── vo/                 # 视图对象
├── service/
│   ├── FoodService         # 食物业务接口
│   ├── DietRecordService   # 饮食记录业务接口
│   └── impl/               # 业务实现
└── util/                   # 工具类
```

## 数据库设计（规划中）

### Schema: `Diet`

**foods 表**
- `food_id` (BigSerial, PK) — 食物唯一标识
- `name` (Unique) — 食物名称
- `category` — 食物分类（如：主食、蔬菜、水果、肉类等）
- `calories_per_100g` — 每100克卡路里
- `protein_per_100g` — 每100克蛋白质（克）
- `fat_per_100g` — 每100克脂肪（克）
- `carbs_per_100g` — 每100克碳水化合物（克）
- `fiber_per_100g` — 每100克纤维素（克）
- `created_at`, `updated_at` — 时间戳

**diet_records 表**
- `record_id` (BigSerial, PK) — 记录唯一标识
- `user_id` (FK → User.users) — 用户ID
- `food_id` (FK → foods) — 食物ID
- `meal_type` — 餐次类型（breakfast/lunch/dinner/snack）
- `amount_grams` — 摄入量（克）
- `record_time` — 记录时间
- `created_at` — 创建时间

**nutrition_goals 表**
- `goal_id` (BigSerial, PK) — 目标唯一标识
- `user_id` (FK → User.users) — 用户ID
- `daily_calories` — 每日卡路里目标
- `daily_protein` — 每日蛋白质目标（克）
- `daily_fat` — 每日脂肪目标（克）
- `daily_carbs` — 每日碳水化合物目标（克）
- `created_at`, `updated_at` — 时间戳

## 关键实现细节

### 与其他服务的交互

- **Orion 服务**：通过 `X-User-Id` 请求头获取当前用户ID（由 Gateway 认证后注入）
- **Gateway 路由**：`/v1/diet/**` → `lb://DietServer`

### PostgreSQL 多 Schema 设计

使用 `Diet` schema，通过 `currentSchema` 连接参数指定默认 schema，与 Orion 的 `User` schema 隔离。

## 外部依赖（规划中）

- **PostgreSQL** — `192.168.3.101:5432/Health`（Diet schema）
- **Redis** — `192.168.3.101:6379`（可选，用于缓存）
- **Nacos** — `192.168.3.101:8848`（配置组：DIET_GROUP）

## 开发优先级

1. **P0 - 基础框架搭建**
   - 注册到 `settings.gradle`
   - 配置数据库连接
   - 实现基础的异常处理

2. **P1 - 食物数据库**
   - 食物实体和 Mapper
   - 食物 CRUD API
   - 食物搜索功能

3. **P2 - 饮食记录**
   - 饮食记录实体和 Mapper
   - 饮食记录 CRUD API
   - 每日营养统计

4. **P3 - 高级功能**
   - 营养目标管理
   - 饮食分析报告
   - 个性化建议
