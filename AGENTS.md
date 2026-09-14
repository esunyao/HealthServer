# 项目总体阅读说明

> [!important]
>
> 1. 先了解整个项目背景、项目意图、项目意义、项目目的、研究背景与未来拓展性。
>
> 2. 必须秉持严谨态度，辩证地看待介绍文件；涉及行为、接口、配置和安全结论时以源码、配置、公开契约和测试证据为准。
>
> 3. 文档按位置各司其职，必须区分：
>    > [!note]
>    >
>    > `<模块>/doc/`：仓库公开的模块大体说明，供 AI 与一般读者快速建立认知，**不展开细节**。
>    >
>    > `<模块>/docp/`：全称 `doc-personal`，本地私有的子项目详细说明；AI **只读参考，不写入**。
>    >
>    > 根 `doc-project/`：特例，专门说明项目整体背景，本地私有，不提交。
>
> 4. 缺少项目背景时，先阅读根 `doc-project/`；缺少模块细节时，再按需阅读对应 `docp/`。
>
> 5. `docp/` 可帮助快速理解设计，但不能替代对当前源码和配置的关键事实核验。
>
> 6. 模块接口、配置、数据结构、架构或行为发生变化时，同步更新受影响模块的 `doc/`。
>
> 7. 继续阅读本文件其余章节。

## 文档位置与命名

| 位置 | 内容 | 详细度 | 提交 | 维护者 |
|---|---|---|---|---|
| 根 `doc-project/` | **项目整体背景**（特例） | 不限 | 否 | 维护者 |
| `<模块>/docp/` | 子项目详细说明 | 很细 | 否 | 维护者 |
| `<模块>/doc/` | 模块大体说明 | 不写太细 | 是 | 维护者与 AI |
| 模块根 `openapi.yaml` | HTTP 接口字段契约 | 以契约为准 | 是 | 维护者 |
| `integration-contracts/src/main/resources/{schema,asyncapi}` | 跨服务事件契约 | 以契约为准 | 是 | 维护者 |
| 根 `AGENTS.md` | 本文件，规范的唯一来源 | — | 是 | 维护者与 AI |
| 根或模块 `CLAUDE.md` | 兼容存根，指向本文件 | — | 是 | 同 `AGENTS.md` |

- 每个模块的 `doc/README.md` 是公开入口；只有确有必要时才增加主题文件。
- 公开文档文件名使用小写英文、单数，不加日期和版本前缀；`README.md` 是入口文件的固定例外。
- `docp/` 的组织方式、文件名和文件头由维护者自行决定，AI 不代为规定，也不写入。
- `doc-project/` 是项目背景特例，不受公开文档命名规则约束。
- 所有模块级 `CLAUDE.md` 若存在，必须是相同格式的两行兼容存根，不维护第二套规则。

## 仓库速查

### 模块

| 模块 | Gradle 模块名 | 默认端口 | 端口变量 | 技术栈 | 职责 |
|---|---|---:|---|---|---|
| `gateway/` | `gateway` | 8091 | `SERVER_PORT` | Spring Cloud Gateway WebFlux + Authentik OIDC | API 网关：路由、限流、日志、认证预处理 |
| `Orion/` | `orion` | 8090 | `SERVER_PORT` | WebMVC + MyBatis-Plus + PostgreSQL + S3 兼容存储 | 用户身份、画像、健康记录、头像文件 |
| `NutriMemo/` | `nutrimemo` | 8099 | `SERVER_PORT` | WebMVC + PostgreSQL + Kafka | 拍照膳食采集、餐次与营养汇总 |
| `HealthMind/` | `healthmind` | 8100 | `HEALTHMIND_PORT` | Spring AI MCP（STREAMABLE）+ Dify + PostgreSQL + Kafka | AI 编排：任务状态、契约校验、事件投递、MCP 授权 |
| `integration-contracts/` | `integration-contracts` | — | — | JSON Schema + AsyncAPI + Kotlin 数据类 | 跨服务事件契约的单一来源 |
| `HealthMindControl/` | 非 Gradle 模块 | 8765 | `HMC_PORT` | FastAPI + Jinja2 + 原生 ES modules（Python `>=3.12,<3.13`） | 本地运维控制台，仅监听 `127.0.0.1` |

> Gradle 项目名为小写；目录名 `Orion` 对应 `:orion`。

### 路由（Gateway → 后端）

| 路径模式 | 目标服务 | 说明 |
|---|---|---|
| `/v1/auth/**`、`/v1/files/avatar/**`、`/v1/users/**` | `lb://Orion` | Gateway 配置中存在；`/v1/auth/**` 与 Orion 当前 OpenAPI 的接口清单关系仍待确认 |
| `/v1/nutri/**` | `lb://NutriMemo` | NutriMemo 对外 API |

路由经 Nacos 服务发现以 `lb://` 协议解析实例地址；每个路由附加 `X-Gateway-Source: HealthServer-Gateway`。

### 技术栈

| 组件 | 版本 |
|---|---|
| Kotlin | 2.3.21 |
| Spring Boot | 4.1.0 |
| Spring Cloud | 2025.1.2 |
| Spring Cloud Alibaba | 2025.1.0.0 |
| Java | 21（toolchain） |
| Gradle | 9.6.1（wrapper） |

### 常用命令

在仓库根目录执行，并确保 `JAVA_HOME` 指向 JDK 21：

```bash
./gradlew build
./gradlew test
./gradlew :gateway:bootRun
./gradlew :orion:bootRun
./gradlew :nutrimemo:bootRun
./gradlew :healthmind:bootRun
./gradlew :orion:test
./gradlew clean
```

`HealthMindControl` 不是 Gradle 模块；其 Python 版本、依赖和测试入口见 `HealthMindControl/README.md`。

## Repository Guidelines

### 项目结构

Kotlin 源码位于各模块 `src/main/kotlin`，资源位于 `src/main/resources`，测试位于 `src/test/kotlin`；数据库迁移位于各模块 `src/main/resources/db/migration`。共享构建与依赖管理在根 `build.gradle`，模块注册在 `settings.gradle`。改动某模块架构前，先阅读该模块的 `doc/README.md`。

### 代码风格与命名

Kotlin 使用四空格缩进和惯用空安全写法；类与对象用 `PascalCase`，函数与属性用 `camelCase`，常量用 `UPPER_SNAKE_CASE`，测试类以 `Test` 结尾。Kotlin 默认包名遵循 `cn.esuny.<模块>`；`integration-contracts` 使用 `cn.esuny.contracts`，HealthMindControl 为 Python 项目。控制器、服务、映射器、模型与配置保持在既有包内。注释简洁，需要解释时使用中文。保留项目既有 Jackson 版本边界和响应式/Servlet 边界。

### 测试

测试使用 JUnit 5、Kotlin test；Orion、NutriMemo、HealthMind 使用 MockK，HealthMind 另使用 Testcontainers 与 MockWebServer。服务与工具优先写聚焦的单元测试，HTTP 契约使用 web/controller 测试。测试放在 `src/test/kotlin` 下与生产代码对应的包中，并以被测类型命名。先运行受影响模块测试，再运行 `./gradlew test`；当前未配置覆盖率阈值。

### 提交与 PR

提交信息使用简短祈使句摘要（如 `Add ...`、`Refactor ...`、`Enhance ...`），每次提交聚焦一件事。PR 说明行为变化、受影响模块、关联议题或计划和验证命令；外部可见变化附 API 示例或截图。涉及 PostgreSQL、Nacos、Kafka、Authentik、Dify 或对象存储的改动必须说明所需环境。

### 安全与配置

JWT 密钥、数据库口令、OAuth Client Secret、Dify API Key 与 S3/RustFS 配置只放在本地或部署配置中，不进入源码控制。运行配置中的外部地址、issuer、数据库、Kafka、Nacos、Dify 和内部服务 URL 全部通过 `.env`、环境变量或 Nacos 注入；被跟踪文件使用空值或不可连接的示例占位符，不写内网地址与真实凭据。测试资源中的 loopback 地址必须明确属于测试。改动认证、网关过滤器、迁移或文件存储时，补充回归测试，并验证令牌类型、用户身份头、schema 变更与错误响应。