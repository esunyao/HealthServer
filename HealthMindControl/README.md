# HealthMindControl v0.2

HealthMind、NutriMemo、Kafka 与 Dify 的本地 Web 运维控制台。只监听 127.0.0.1:8765，不开放到局域网/公网；
所有数据库与 Kafka 写操作都必须「预览 → 输入确认文本 → 事务执行」，并双写审计（DB + JSONL）。

v0.2 变更：后端按领域分包、前端多视图 + 主题系统（4 基色 × 6 强调色 + 跟随系统）、
无 npm/CDN 的现代组件化 UI（htmx 风格属性 + Web Components）、需求合规缺口全部补齐
（详见 docs/requirements.md）。

## 1. 环境准备（只使用父目录虚拟环境）

```powershell
cd E:\ProjectSpace\HealthServer
\.venv\Scripts\Activate.ps1
$env:UV_PROJECT_ENVIRONMENT = "E:\ProjectSpace\HealthServer\.venv"
uv sync --project HealthMindControl --extra test
```

## 2. 配置 .env

```powershell
Copy-Item .env.example .env   # 然后编辑
```

| 配置项 | 用途 |
|---|---|
| HMC_DATABASE_DSN | PostgreSQL，同时访问 healthmind / nutri schema |
| HMC_NUTRI_DATABASE_DSN | 可选（Nutri 独立库时） |
| HMC_KAFKA_BOOTSTRAP_SERVERS | Kafka 地址（逗号分隔） |
| HMC_DIFY_URL / HMC_MCP_URL / HMC_AUTH_URL | Dify / MCP / Authentik |
| HMC_DIFYCTL_PATH | difyctl.exe 路径 |
| HMC_DIFY_CONSOLE_TOKEN | 可选：只读自动读取 published workflow |
| HMC_STALE_MINUTES / HMC_REFRESH_SECONDS | 滞留判定 / SSE 间隔 |
| HMC_KAFKA_MAX_SCAN_MESSAGES | 消息查看扫描上限（默认 50000） |
| HMC_KAFKA_SECURITY_PROTOCOL | 默认 PLAINTEXT；集群启用认证时填 SASL_PLAINTEXT / SSL / SASL_SSL |
| HMC_KAFKA_SASL_MECHANISM / _USERNAME / _PASSWORD | SASL 认证（凭据只在本机 .env，不入库/审计） |
| HMC_KAFKA_SSL_CA_LOCATION | 自定义 CA 证书路径（SSL/SASL_SSL 时可选） |
| HMC_KAFKA_METADATA_CACHE_SECONDS / HMC_PROBE_CACHE_TTL_SECONDS | 缓存节流 |
| HMC_PREVIEW_TTL_SECONDS / HMC_TASK_RETENTION_DAYS | 预览令牌 / 克隆保留期 |

## 3. 启动与访问

```powershell
cd E:\ProjectSpace\HealthServer\HealthMindControl
uv run --active --project . healthmind-control
```

浏览器打开 http://127.0.0.1:8765（自动跳转 /ui/dashboard）。

## 4. 页面

总览（SSE 5s 轻量 + 昂贵按需）、任务、数据浏览（healthmind/nutri 受控行浏览器，keyset 分页 ≤100、
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
├─ config.py security.py audit.py models.py util.py
├─ db/database.py          # 连接池 + 表结构自检 + 15s statement_timeout
├─ services/               # kafka / dify
├─ repositories/           # overview tasks rows trace releases recovery → 门面 Repository
├─ api/                    # overview tasks rows trace kafka releases recovery auditlog events
├─ ui/                     # page（视图路由）/ parts（片段）/ fmt（模板辅助）
├─ templates/              # base + views/* + partials/*
└─ static/                 # css（tokens/theme/base/components/views） js（模块 + views/*） img
tests/                     # pytest 单测（无外部依赖）+ _smoke.py 可选真库冒烟
docs/requirements.md       # 需求合规矩阵与 V1.1 清单
```

约定：模板全局 fmt_ts / col_label / badge_cls 见 ui/fmt.py；前端 hx-* 属性为 htmx 兼容子集
（js/hx.js 驱动，官方 htmx.min.js 可原样替换）；CSRF 走 <meta name=csrf>；预览流统一 js/flow.js。

## 6. 测试

```powershell
cd E:\ProjectSpace\HealthServer
\.venv\Scripts\python.exe -m pytest -q HealthMindControl\tests
\.venv\Scripts\python.exe HealthMindControl\tests\_smoke.py   # 需要 .env 可达真库（可选）
```

JS 语法由 pytest 用 node --check 递归校验（node 缺失自动跳过）。

## 7. 安全与边界（沿用 + v0.2）

- Kafka 消息查看绝不提交业务消费组 offset；控制台自身诊断组（healthmind-control-*）不在列表中展示。
- 所有写操作：预览令牌 120s（可配）+ 记录快照哈希绑定；恢复 attempt 另有行锁与 lock_version 双校验。
- HealthMind 收件箱不存 payload：缺失 → 重放 capture-ready；已存在 → 只允许克隆任务（不重置原 inbox）。
- 审计：var/audit/admin-actions.jsonl（portalocker + fsync），DB workflow_release_audits 每变更同写。
- Dify API Key 只由 Nacos/环境变量管理；difyctl 导出永不加 --include-secret；不读取凭据文件。
- v1 不做：topic 创建/删除、消费组 offset 重置、Kafka 配置修改、任意 SQL、物理删除、修改历史成功记录。