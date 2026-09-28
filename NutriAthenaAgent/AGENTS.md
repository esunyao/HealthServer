# NutriAthenaAgent — AI 导航

根 [`../AGENTS.md`](../AGENTS.md) 是仓库级规范；本文件说明模块边界和代码入口。实现以源码、[`pyproject.toml`](./pyproject.toml)、[`uv.lock`](./uv.lock) 与自动测试为准。

## 模块边界

本模块拥有 HealthMind-compatible HTTP run API、JWT 校验、独立 PostgreSQL schema、持久化 worker、餐食分析 runner、只读 HealthMind MCP 客户端和本目录工程。它不拥有 HealthMind 业务记录、Kafka、NutriMemo/Orion 业务服务或跨模块数据库迁移。不得从 Agent 写入业务数据或绕过 HealthMind 的授权流程。

餐食 prompt/营养推理规则沿用相邻 `../AgentDeveloper/skills/`。运行端可适配执行方式，但本任务范围不调整 prompt 文本、工具编排策略或营养估算规则。

## 快速事实

| 项 | 值 |
|---|---|
| Python 包 | `nutriathena_agent`，Python 3.11+，`uv` 管理，`src/` 布局 |
| 服务入口 | `nutriathena-agent serve`，FastAPI + PostgreSQL worker |
| CLI | `nutriathena-agent migrate/serve/smoke/meal/graph/agent`；兼容旧 `agentdevelop` 脚本名 |
| 数据库 | 独立 `nutriathena_agent` schema；版本 SQL 位于 [`migrations/`](./migrations/) |
| HTTP 契约 | [`doc/README.md`](./doc/README.md)；仓库级对接定义见 `HealthMind/doc/agent-runtime.md` |
| 主要依赖 | FastAPI、Psycopg 3、PyJWT、MCP Python SDK、LangGraph/DeepAgents |
| 测试 | [`tests/`](./tests/)；默认不连接真实 OAuth、MCP、模型或生产数据库 |

## 代码地图

| 文件 | 职责 |
|---|---|
| [`src/nutriathena_agent/api.py`](./src/nutriathena_agent/api.py) | HealthMind 线程/run HTTP 契约、JWT 依赖、显式数据库迁移入口 |
| [`src/nutriathena_agent/database.py`](./src/nutriathena_agent/database.py) | 线程/run 幂等、持久化队列、worker 租约 fencing、取消与保留清理 |
| [`src/nutriathena_agent/worker.py`](./src/nutriathena_agent/worker.py) | pending claim、心跳续租、超时/取消、调用 runner、条件终态写入 |
| [`src/nutriathena_agent/auth.py`](./src/nutriathena_agent/auth.py) | JWKS 签名、issuer/audience/caller/scope 验证 |
| [`src/nutriathena_agent/runtime_config.py`](./src/nutriathena_agent/runtime_config.py) | 服务、数据库、OAuth、部署与 worker 配置 |
| [`src/nutriathena_agent/meal_agent.py`](./src/nutriathena_agent/meal_agent.py) | 可替换 `MealRunner` 协议和现有 DeepAgent meal graph 适配 |
| [`src/nutriathena_agent/mcp_tools.py`](./src/nutriathena_agent/mcp_tools.py) | MCP SDK session、稳定 `_meta.tool_call_id`、授权上下文预取与脱敏 |
| [`src/nutriathena_agent/images.py`](./src/nutriathena_agent/images.py) | MCP 授权图片的主机白名单、大小/MIME 限制和内存多模态编码 |
| [`src/nutriathena_agent/contracts.py`](./src/nutriathena_agent/contracts.py) | 餐食成功与 `needs_review` 结果契约 |
| [`src/nutriathena_agent/artifact.py`](./src/nutriathena_agent/artifact.py) | 从实际运行代码、迁移、prompt 资产和锁文件计算 SHA-256 |
| [`src/nutriathena_agent/migrations.py`](./src/nutriathena_agent/migrations.py) | 版本 SQL 校验和账本、显式迁移 |
| [`src/nutriathena_agent/smoke.py`](./src/nutriathena_agent/smoke.py) | 安全真实端到端 smoke；提交后通过 list-runs 对账，不打印餐食详情 |

## 重要运行约束

- 一次 HealthMind attempt 固定一个 `thread_id`、一个 `attempt_id` 和至多一个 run；同请求摘要重试返回原 run，不同请求摘要为 409。
- Postgres 中只有 pending 可 claim。running 由 lease owner/version fencing；进程失联后超时 run 标 interrupted，不重放模型调用。
- `result_expires_at` 不早于完成后 24 小时；幂等 run/thread 元数据保留至少 180 天。新迁移必须编号递增，已应用 SQL 不得改写。
- HealthMind MCP 的 `tool_call_id` 放在 MCP `_meta`，不是业务参数；UUIDv5 名称必须使用完整工具 code `nutrimemo.capture_context.get` / `orion.nutrition_context.get`。capture 为下载授权图片在模型前预取一次，wrapper 返回脱敏缓存；nutrition 保留原模型驱动的调用时序；每个工具每 attempt 最多远端读取一次。
- signed image URL 仅供 worker 下载；要求显式 host allowlist，不允许重定向。URL、token、原始 capture ID 不进入模型上下文或常规日志。
- 不读、不打印或提交 `.env`、OAuth token、模型 key、图片或真实餐食输出。真实 smoke 只能使用已有授权 task/attempt 和用户提供的测试上下文。
- `artifact_sha256` 从当前加载代码、迁移、模型 prompt 资产和 lock 文件计算，不能回显调用请求中的值。

## 本地验证

```bash
uv sync --extra test
uv run pytest -q
uv run nutriathena-agent graph
```

数据库迁移和真实 smoke 需要各自配置的非生产测试环境；不要通过清空现有业务库来验证迁移。真实 smoke 的准备说明见 [`README.md`](./README.md) 与 [`doc/README.md`](./doc/README.md)。
