# NutriAthenaAgent

NutriAthenaAgent 是为 HealthMind 提供持久化执行能力的餐食分析运行服务。HealthMind 创建一次分析尝试（attempt）后，通过 HTTP 调用本服务；服务先将请求保存到 PostgreSQL，再由持有租约的工作进程（worker）执行餐食分析流程，最后由 HealthMind 获取结果。本模块同时保留两个小型 LangGraph/LangChain 教学示例。

## 启动服务

使用 Python 3.11 及以上版本，通过 `uv` 管理依赖：

```bash
cd NutriAthenaAgent
uv sync --extra test
```

将 `.env.example` 复制为 `.env`，配置运行参数、数据库、OAuth 签发方（issuer）与 JWKS、模型，以及只读的 HealthMind MCP 客户端。不要提交 `.env`，也不要在命令行参数中填写凭据。为兼容已有本地环境，旧的 `AGENTDEVELOP_*` 模型和 MCP 环境变量仍可作为回退配置。

启动服务前，先执行版本化 SQL 迁移：

```bash
uv run nutriathena-agent migrate
uv run nutriathena-agent serve
```

HTTP 服务监听 `NUTRIATHENA_HOST:NUTRIATHENA_PORT`，默认地址为 `0.0.0.0:8101`。`GET /healthz` 用于检查数据库连通性。需要认证的接口要求携带 OAuth Bearer Token，并校验配置的签发方、受众（audience）、允许的调用方 ID 和 `healthmind.agent.run` 权限范围（scope）。

HealthMind 运行协议见 [`doc/README.md`](./doc/README.md)。本服务为每次 attempt 创建绑定的线程（thread），返回 HealthMind 要求的固定 task/attempt 身份元数据；每次 attempt 最多接收一个幂等运行记录（run），提供待执行、执行中和终态查询，尽力响应取消请求，并将成功结果保留至少 24 小时。PostgreSQL 使用独立的 `nutriathena_agent` schema；本服务没有跨 schema 外键，也不写入 HealthMind 的业务记录。

## 真实环境冒烟测试

`smoke` 通过已部署的 HTTP 服务发送一次真实请求。如果提交结果不明确，会查询已有 run 进行核对，然后等待执行结果。输出仅包含 ID、状态、摘要和菜品数量，不打印访问令牌、图片 URL 或食物名称。测试必须使用已获授权的 task 和 attempt，并确保对应餐食图片可用；命令不会自动构造任务上下文或示例结果。

```bash
uv run nutriathena-agent smoke \
  --task-id <authorized-task-uuid> \
  --attempt-id <authorized-attempt-uuid> \
  --trace-id <trace-id>
```

在本地配置 `NUTRIATHENA_SMOKE_TOKEN_URL`、`NUTRIATHENA_SMOKE_CLIENT_ID` 和 `NUTRIATHENA_SMOKE_CLIENT_SECRET`。使用相同 attempt 和相同请求重复执行时，会复用已有 run；如果修改已有 attempt 的请求内容，则会因幂等冲突而被拒绝。

## 测试与教学命令

默认自动化测试使用可替换的执行器和模拟依赖，无需连接真实 OAuth、MCP 或模型服务；PostgreSQL 集成测试需要 Docker：

```bash
uv run pytest -q
uv run nutriathena-agent graph
uv run nutriathena-agent graph "嗯"
uv run nutriathena-agent agent "统计一下这句话的词数：晚饭吃了清蒸鲈鱼"
```

`meal` 命令通过 MCP 和模型运行端直接执行一次已获授权的 attempt。生产任务应通过 `serve` 接入，以使用 PostgreSQL 提供的幂等控制、执行租约、数据保留和取消机制。

## 调试模式

默认关闭。通过环境变量 `NUTRIATHENA_DEBUG` 或 `serve`/`meal` 子命令的 `--debug` 开启；CLI 优先于环境变量：

```bash
NUTRIATHENA_DEBUG=trace uv run nutriathena-agent serve
uv run nutriathena-agent meal --debug --task-id <uuid> --attempt-id <uuid>
uv run nutriathena-agent meal --debug full --task-id <uuid> --attempt-id <uuid>
```

| 级别 | 输出 |
|---|---|
| `off`（默认） | 不改变现有日志行为 |
| `trace` | 结构化轨迹：run 起止、LangGraph 节点、模型/工具调用、耗时、token 与终态；不含提示词、图片、URL 或餐食内容 |
| `full` | 在 `trace` 基础上输出模型输入/输出、工具入参与返回及最终结果原文；仅限本地开发 |

调试事件写入 stderr。`full` 会包含真实餐食备注与模型输出，且仍会移除图片 data URL、签名 URL、Bearer/JWT 与常见敏感键；不要在生产环境开启。

## 餐食分析边界

- 餐食提示词和膳食技能沿用同级目录 [`AgentDeveloper/skills`](../AgentDeveloper/skills/) 中维护的资产，本服务将现有分析流程适配为可替换的执行器。
- 每次 attempt 在视觉模型调用前预取一次餐食采集 MCP 上下文，以获得已授权的图片 URL；面向模型的工具返回脱敏后的缓存上下文。营养画像 MCP 工具仍由模型按原有时序调用。稳定审计 ID 使用 attempt UUID 和完整 MCP 工具代码派生的 UUIDv5，通过 MCP `_meta.tool_call_id` 传递；每个工具在一次 attempt 中最多远程读取一次。
- 餐食采集上下文包含可空的餐食备注 `notes`。备注作为数据传入视觉分析流程，不能覆盖系统指令。
- 仅下载已授权采集记录返回的签名图片 URL。下载主机必须通过 `NUTRIATHENA_MEDIA_ALLOWED_HOSTS` 显式加入白名单；重定向、不支持的 MIME 类型或文件签名、图片数量超限、响应体大小超限都会被拒绝。图片 URL 和原始字节不会作为工具上下文或服务输出暴露给模型；视觉输入使用经过校验的内存编码图片。
- 采集图片缺失或不可用时，返回现有 `needs_review`（需要复核）结果，不会将其声称为成功完成的模型分析。
- 当前生产运行没有食物成分检索数据源。提示词明确声明未提供证据，允许基于常见食物知识进行保守估算并降低置信度，同时禁止伪造引用或声称进行过检索。
- 模型不具备 Shell、文件系统、写入、删除或子 Agent 工具。业务侧授权与结果持久化仍由 HealthMind 负责。
