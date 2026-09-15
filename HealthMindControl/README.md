# HealthMindControl v0.3

HealthMind、NutriMemo、Kafka 与 Dify 的本地 Web 运维控制台。只监听 127.0.0.1:8765，不开放到局域网/公网；
所有数据库与 Kafka 写操作都必须「预览 → 输入确认文本 → 事务执行」，并双写审计（DB + JSONL）。

v0.3 新增链路实验台、原始 Kafka JSON 无损投递、服务端绑定的写操作预览、专家 SQL 与离线消费组
offset 工具，并强化任务重试、attempt 恢复和取消任务的业务闭环。

## 1. 环境准备（模块自己的 `.venv`）

```powershell
cd E:\ProjectSpace\HealthServer
uv sync --project HealthMindControl --python 3.12 --extra test
```

## 2. 配置 .env

```powershell
Copy-Item HealthMindControl\.env.example HealthMindControl\.env   # 然后编辑模块目录下的 .env
```

| 配置项 | 用途 |
|---|---|
| HMC_HOST / HMC_PORT | 本地监听地址和端口（默认 `127.0.0.1:8765`） |
| HMC_DATABASE_DSN | PostgreSQL，同时访问 healthmind / nutri schema |
| HMC_NUTRI_DATABASE_DSN | 可选（Nutri 独立库时） |
| HMC_KAFKA_BOOTSTRAP_SERVERS | Kafka 地址（逗号分隔） |
| HMC_DIFY_URL / HMC_MCP_URL / HMC_AUTH_URL | Dify / MCP / Authentik |
| HMC_DIFYCTL_PATH | difyctl.exe 路径 |
| HMC_NUTRI_API_URL | 实验台调用 NutriMemo API 的地址（可选） |
| HMC_ENABLE_EXPERT_MODE | `true` 才显示专家 SQL / offset 工具，默认 `false` |
| HMC_DEBUG_DB_PATH | 调试运行和步骤历史的本地 SQLite 文件 |
| HMC_DIFY_CONSOLE_TOKEN | 可选：只读自动读取 published workflow |
| HMC_STALE_MINUTES / HMC_REFRESH_SECONDS | 滞留判定 / SSE 间隔 |
| HMC_KAFKA_MAX_SCAN_MESSAGES | 消息查看扫描上限（默认 50000） |
| HMC_KAFKA_SECURITY_PROTOCOL | 默认 PLAINTEXT；集群启用认证时填 SASL_PLAINTEXT / SSL / SASL_SSL |
| HMC_KAFKA_SASL_MECHANISM / _USERNAME / _PASSWORD | SASL 认证（凭据只在本机 .env，不入库/审计） |
| HMC_KAFKA_SSL_CA_LOCATION | 自定义 CA 证书路径（SSL/SASL_SSL 时可选） |
| HMC_KAFKA_METADATA_CACHE_SECONDS / HMC_PROBE_CACHE_TTL_SECONDS | 缓存节流 |
| HMC_QUERY_LIMIT | 受控列表默认查询上限 |
| HMC_AUDIT_PATH | JSONL 审计文件路径 |
| HMC_PREVIEW_TTL_SECONDS / HMC_TASK_RETENTION_DAYS | 预览令牌 / 克隆保留期 |

## 3. 启动与访问

```powershell
cd E:\ProjectSpace\HealthServer
uv run --project HealthMindControl healthmind-control
```

浏览器打开 http://127.0.0.1:8765（自动跳转 /ui/dashboard）。

## 4. 页面

总览（SSE 5s 轻量 + 昂贵按需）、链路实验台（逐步暂停/放行/直调/观察）、任务、数据浏览（healthmind/nutri 受控行浏览器，keyset 分页 ≤100、
payload 延迟、脱敏）、链路（关系优先时间线 + 模糊命中标注）、Kafka（分区健康/成员/offsets/只读消息
含时间与结构化过滤/受控生产）、Dify 版本（candidate→绑定工具→production→退役/回滚，含审计）、
受控修复（一键诊断 + 手动 + 克隆 + attempt 恢复语义闭环）、审计（JSONL + DB）、关于。

### 服务卡片与认证说明
卡片是「可达性探活」，不携带业务凭据：Dify /v1/info 返回 401+Bearer challenge 视为可达；
MCP / Authentik 若在认证网关后返回 401/403/405/429 也视为“可达但需认证”（副标题显示 HTTP 状态码）。
Kafka 如需 SASL/SSL 按上表在 .env 配置。总览卡片由 SSE 轻量摘要 + 完整 /api/status 合并刷新，
不会因 SSE 每 5s 推送把 Kafka/Dify/MCP/Authentik 误显示为不可用。

### 主题切换
右上角 ◐：4 基色（midnight 默认 / light / slate / olive）× 6 强调色 + 跟随系统；持久化于 localStorage
（hmc.theme）；切换带颜色过渡，状态翻转有脉冲动画。

## 5. 项目结构

```
src/healthmind_control/
├─ main.py / app.py        # 入口与薄装配（lifespan 注入 + routers）
├─ config.py security.py audit.py models.py util.py debug_store.py
├─ db/database.py          # 连接池 + 表结构自检 + 15s statement_timeout
├─ services/               # kafka / dify / debug / expert
├─ repositories/           # overview tasks rows trace releases recovery → 门面 Repository
├─ api/                    # overview tasks rows trace kafka releases recovery auditlog events
├─ ui/                     # page（视图路由）/ parts（片段）/ fmt（模板辅助）
├─ templates/              # base + views/* + partials/*
└─ static/                 # css（tokens/theme/base/components/views） js（模块 + views/*） img
tests/                     # pytest 单测（无外部依赖）+ _smoke.py 可选真库冒烟
doc/requirements.md       # 公开合规状态摘要（三态）
```

约定：模板全局 fmt_ts / col_label / badge_cls 见 ui/fmt.py；前端 hx-* 属性为 htmx 兼容子集
（js/hx.js 驱动，官方 htmx.min.js 可原样替换）；CSRF 走 <meta name=csrf>；预览流统一 js/flow.js。

## 6. 测试

```powershell
cd E:\ProjectSpace\HealthServer
uv run --project HealthMindControl pytest -q
uv run --project HealthMindControl python HealthMindControl\tests\_smoke.py
```

JS 语法由 pytest 用 node --check 递归校验（node 缺失自动跳过）。

## 7. 安全与边界（v0.3）

- Kafka 消息查看绝不提交业务消费组 offset；控制台自身诊断组（healthmind-control-*）不在列表中展示。
- 所有写操作经过预览令牌和确认链路；执行请求不能覆盖预览时保存的参数。
- HealthMind 收件箱不存 payload；缺失时支持重放 capture-ready，已存在时不会重置原 inbox。任务克隆与 release/task 约束仍以公开合规摘要为准。
- 审计：var/audit/admin-actions.jsonl（portalocker + fsync），DB workflow_release_audits 每变更同写。
- Dify API Key 只由 Nacos/环境变量管理；difyctl 导出永不加 --include-secret；不读取凭据文件。
- 专家模式允许单条 SQL 和离线消费组 offset 调整；默认关闭，仍不提供 topic 创建/删除、物理删除向导或修改历史成功记录的普通表单。
- Kafka payload 始终以编辑器原始 UTF-8 文本发送；服务端负责 JSON 校验，避免浏览器把 BIGINT 四舍五入。
- 详细链路与每阶段数据库/Kafka 变化见 [AI 分析链路](doc/analysis-chain.md)。
