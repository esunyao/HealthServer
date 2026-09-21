# HealthMindControl — AI 工作指南（导航）

> 本文件只做导航与理解，不新增规范；规范来源是根 [`AGENTS.md`](../AGENTS.md) 与 [`doc/README.md`](./doc/README.md)。行为与安全边界以源码、[`pyproject.toml`](./pyproject.toml) 与测试为准。

## 这个模块是什么

**本地运维控制台**（v0.4）：HealthMind、NutriMemo、Kafka 与 Dify 的 Web 运维界面。只监听 `127.0.0.1:8765`，不开放到局域网/公网；所有数据库与 Kafka 写操作必须「预览 → 输入确认文本 → 事务执行」，并双写审计（DB + JSONL）。

边界：
- owns：诊断视图（总览/任务/数据浏览/链路/Kafka/Dify Release 版本管理/受控修复/审计）、链路实验台、白名单数据构造与 MCP 手动测试数据。
- not owns：业务数据本身（不改 Nutri 业务数据、不代发业务 Kafka 消息、不调 Dify 执行）；它只是观察与受控操作工具。
- 运行环境为本机：不要把它部署为服务或加入 Gateway 路由。

## 快速事实

| 项 | 值 |
|---|---|
| 类型 | 非 Gradle 模块；Python `>=3.12,<3.13`，uv 管理（[`pyproject.toml`](./pyproject.toml)、`uv.lock`） |
| 入口 | [`src/healthmind_control/main.py`](./src/healthmind_control/main.py)（console script `healthmind-control`）；[`app.py`](./src/healthmind_control/app.py) 为薄装配 |
| 端口/地址 | `HMC_HOST`（默认并强制 `127.0.0.1`）、`HMC_PORT`（默认 `8765`）；Windows 上强制 Selector 事件循环 |
| 技术栈 | FastAPI + Jinja2 + 原生 ES modules（自研 hx.js 兼容子集）+ psycopg 连接池 + confluent-kafka（锁 `>=2.14.2,<2.15`，2.15.0 Windows wheel 缺 admin 包） |
| 配置 | 模块自己的 `.env`（模板见 [`.env.example`](./.env.example)；AI 不读实际 `.env` 内容）；全部 `HMC_*` 变量见 [README.md](./README.md) 第 2 节 |
| 文档 | [`doc/`](./doc/)：README（大体说明）、`analysis-chain.md`（链路与排障）、`fixture.md`（数据构造）、`requirements.md`（公开合规三态） |

## 代码地图

| 位置 | 职责 |
|---|---|
| [`config.py`](./src/healthmind_control/config.py) | pydantic-settings 加载 `HMC_*` |
| [`security.py`](./src/healthmind_control/security.py) / [`audit.py`](./src/healthmind_control/audit.py) | CSRF 与预览令牌；JSONL 审计（异步线程 + portalocker + fsync + 轮转） |
| [`db/database.py`](./src/healthmind_control/db/database.py) | 连接池、表结构自检、15s `statement_timeout` |
| [`services/`](./src/healthmind_control/services/) | `kafka.py`（诊断，不提交业务消费组 offset）、`dify.py`（经 difyctl 只读）、`debug.py`（链路实验台）、`expert.py`（专家 SQL/offset）、`events.py`（SSE）、`fixture_reaper.py`（测试数据到期回收） |
| [`repositories/`](./src/healthmind_control/repositories/) | 门面 Repository：overview/tasks/fixtures/rows/trace/releases/recovery |
| [`api/`](./src/healthmind_control/api/) | 12 个路由模块（overview/tasks/fixtures/rows/trace/kafka/releases/recovery/auditlog/debug/expert/events） |
| [`ui/`](./src/healthmind_control/ui/) | `page.py`（视图路由）、`parts.py`（片段）、`fmt.py`（模板全局 fmt_ts/col_label/badge_cls） |
| [`templates/`](./src/healthmind_control/templates/) | `base.html` + `views/`（11 页）+ `partials/` |
| [`static/`](./src/healthmind_control/static/) | css/js（`hx.js` 驱动 htmx 兼容子集、`flow.js` 预览流）、img |
| [`debug_store.py`](./src/healthmind_control/debug_store.py) | 调试运行与步骤历史（SQLite，`var/debug/control.sqlite3`） |

## 任务 → 读什么

| 你要做的事 | 先读 |
|---|---|
| 了解 AI 分析链路与排障 | [doc/analysis-chain.md](./doc/analysis-chain.md)（逐阶段状态表 + 故障定位顺序） |
| 改数据构造/MCP 手测 | [doc/fixture.md](./doc/fixture.md) + [`services/fixture_reaper.py`](./src/healthmind_control/services/fixture_reaper.py) + [`api/fixtures.py`](./src/healthmind_control/api/fixtures.py) |
| 改写操作链路（预览/确认/审计） | [`security.py`](./src/healthmind_control/security.py) + [`audit.py`](./src/healthmind_control/audit.py) + 对应 `api/` 路由 |
| 改 Kafka 诊断 | [`services/kafka.py`](./src/healthmind_control/services/kafka.py) + [`api/kafka.py`](./src/healthmind_control/api/kafka.py) |
| 改 Dify 版本页 | [`services/dify.py`](./src/healthmind_control/services/dify.py) + [`repositories/releases.py`](./src/healthmind_control/repositories/releases.py) |
| 改前端交互 | [`static/js/`](./src/healthmind_control/static/js/)（hx.js/flow.js 约定）+ [`ui/fmt.py`](./src/healthmind_control/ui/fmt.py) + `templates/` |
| 看合规状态 | [doc/requirements.md](./doc/requirements.md)（公开三态摘要） |

## 关键事实与易错点

- **主机锁定**：`main.py` 强制 `HMC_HOST=127.0.0.1`；任何要求开放监听的改动都属于安全边界变更，默认拒绝。
- **写操作三件套**：预览令牌绑定参数 → 用户输入确认文本 → 事务执行；执行请求不能覆盖预览时保存的参数。新增任何写操作必须复用该链路并写审计。
- **审计双写**：DB `workflow_release_audits` + JSONL `var/audit/admin-actions.jsonl`（50 MiB 轮转、默认保留 90 天）；两类记录语义不同，不要只保留其一。
- **专家模式默认关闭**：启用后也只允许单条 SQL（pglast 解析）与无在线成员的消费组 offset 调整；Kafka payload 始终以原始 UTF-8 文本发送，避免浏览器把 BIGINT 四舍五入。
- **不提交业务消费组 offset**：消息查看用控制台自有诊断组（`healthmind-control-*`，不在列表展示）；控制台绝不代业务消费。
- **MCP 手测隔离**：只构造 `ai_tasks(running)+ai_task_attempts(running)` 供 Dify 草稿测试，不调 Dify、不发 Kafka、不改 Nutri 数据；租期默认 50 分钟（范围 5–55），到期由 reaper 标 cancelled；构造出的 outbox 默认 `next_attempt_at` 保持到 2099，需显式「隔离 outbox 放行」才进入发布流程。
- **HealthMind inbox 不存 payload**：缺失时支持重放 capture-ready，已存在时不会重置原 inbox。
- **JS 由 pytest 校验语法**：测试用 `node --check` 递归检查前端 JS（无 node 时自动跳过）；改前端后至少跑 pytest。
- 测试环境注意：`confluent-kafka` 版本被刻意锁定，升级前先确认 Windows wheel 含 admin 包。

## 测试与验证

```powershell
uv sync --project HealthMindControl --python 3.12 --extra test
uv run --project HealthMindControl pytest -q
uv run --project HealthMindControl python HealthMindControl\tests\_smoke.py   # 可选，真库冒烟
```

- 测试在 [`tests/`](./tests/)：10 个 `test_*.py`（canonical_parity、config、control_plane、core、database_recovery、dify_service、fixtures、frontend_dom、kafka_config、stability_fixes）+ `_smoke.py` + `hx_driver_check.mjs`。
- 真实 PostgreSQL/Kafka/Dify/MCP 操作不由自动测试执行，必须由操作者在页面逐步预览确认。

## 相关文档

- [README.md](./README.md) — 运行手册（环境、`.env` 变量、页面、最短 MCP 草稿测试）。
- [doc/README.md](./doc/README.md) — 模块大体说明与合规状态指引。
- [../AGENTS.md](../AGENTS.md) — 仓库规范、阅读导航与项目背景。
- 被观测/操作的服务（本控制台的下钻出口）：[../HealthMind/AGENTS.md](../HealthMind/AGENTS.md)（任务与 MCP 授权）、[../NutriMemo/AGENTS.md](../NutriMemo/AGENTS.md)（采集与回写）、[../Orion/AGENTS.md](../Orion/AGENTS.md)（营养上下文来源）。
- [../integration-contracts/AGENTS.md](../integration-contracts/AGENTS.md) — 链路事件的字段契约与物理 topic。
- 私有：`docp/`（若存在）是维护者详细核查材料，AI 只读参考、不写入。
