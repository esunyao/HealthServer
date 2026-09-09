# HealthMindControl 需求与合规清单

版本：v0.2（结构重整 + 主题 + 网页现代化 + 缺口补齐）
更新：随实施保持同步；✅ 已实现 / ⚠️ 部分（注明残余）/ ❌ 未实现（注明原因）

## 1. 总览仪表盘

| 需求 | 状态 | 说明 |
|---|---|---|
| PG/Kafka/Dify/MCP/Authentik 连通 | ✅ | /api/status 全量 + 卡片化；DB 摘要走 SSE |
| Dify /v1/info 401+Bearer 视为可达 | ✅ | probe(expected_401)，单测覆盖 |
| production 版本与绑定工具 | ✅ | status_light 投影列 + 工具 code/scope 列表卡片 |
| 任务状态数/最近失败原因/耗时 | ✅ | recent_failures 带 duration_ms；SSE 推送计数 |
| inbox/outbox 待处理/失败/滞留 | ✅ | backlogs counts + 多类滞留 + 一键跳修复 |
| topic 分区/leader/ISR/lag | ✅ | Kafka 概览卡（分区健康徽章、消费组 lag），元数据带 8s 缓存 |
| 5s SSE + 昂贵按需 | ✅ | SSE 仅轻量摘要；Kafka/滞留 30s 自动或手动；隐藏标签页暂停 |

## 2. Kafka 管理

| 需求 | 状态 | 说明 |
|---|---|---|
| broker/topic/partition/leader/replica/ISR | ✅ | metadata() |
| earliest/latest offset | ✅ | 分区级 low/high |
| 消费组 offset/lag/成员 | ✅ | describe_consumer_groups 成员 + assignment；按组 offsets/lag 明细；自身诊断组隐藏 |
| 业务 topic 动态查看 | ✅ | 概览业务卡 + Kafka 页全表 |
| 按 offset/时间/最新/最早读取 | ✅ | start=offset/time/earliest/latest（offsets_for_times） |
| 按 topic/partition/key/event/trace/type 过滤 | ✅ | 服务端过滤 + contains 兜底；扫描上限 5 万条可配 |
| key/headers/payload/时间戳/offset 查看 | ✅ | 消息行 + 抽屉（JSON 树 + 原始） |
| 只读不提交 | ✅ | 每次读取独立临时组；enable.auto.commit/store=false；自组不展示 |
| 高级生产（校验/预览/警告强制/原因+确认/交付报告） | ✅ | headers 编辑器、业务模板、force、delivery 报告；不支持 topic 删除/offset 重置/配置修改 |

## 3. 数据库滞留与链路查询

| 需求 | 状态 | 说明 |
|---|---|---|
| 两 schema 受控行浏览 | ✅ | /api/rows + /api/rows/meta + 数据浏览页（allowlist 注册表 13 表） |
| 状态/时间/错误码/服务/用户/ID 筛选 | ✅ | 按 kind 可用列动态展示；等值 + 时间范围 |
| keyset 分页 ≤100 + payload 延迟 | ✅ | (created_at,id) 双键 opaque cursor；列表去大 JSONB 列，详情抽屉按需取全字段（脱敏） |
| 6 类 ID 链路搜索 | ✅ | trace 引擎关系优先（request_event_id / payload_sha256 连接 / meal↔capture），ILIKE 兜底标模糊命中 |
| 时间线展示 | ✅ | 链路页按 STAGES 顺序渲染，异常红色、模糊黄色角标、节点详情抽屉 |
| 滞留识别 | ✅ | queued/running、attempt 超 timeout、processing inbox、published 无下游、meal/任务不一致 |
| 默认隐藏敏感 | ✅ | 敏感 key 名单 + 签名 URL 参数截断；全出口统一 redact |

## 4. Dify 版本管理

| 需求 | 状态 | 说明 |
|---|---|---|
| difyctl 发现 workspace/app/输入字段/DSL | ✅ | discover(workspaces/apps/describe/export DSL)；探明本机 difyctl CLI |
| publish JSON 粘贴 / Console token 只读读取 | ✅ | 向导按钮 ①②③ + /api/dify/analyze（JSON/DSL 双解析） |
| 字段提取与确认 | ✅ | 自动回填逐字段可改；input schema 由 DSL user_input_form 生成草案并提示人工核对 |
| canonical/schema hash 与 Kotlin 一致 | ✅ | 新增对照测试：直接重算 V2 seed 中三个既有 sha256 列 |
| candidate/绑定工具/提升/退役/回滚 | ✅ | bind_tools 仅 candidate；迁移放宽审计 action（V3） |
| 每次变更双写 DB 审计 + JSONL | ✅ | create/transition/bind_tools 一致；审计页可见两路 |
| API Key 不入 release 表 | ✅ | 保持 |

## 5. 受控修复

| 需求 | 状态 | 说明 |
|---|---|---|
| 预览 → 事务；120s 令牌 + 快照哈希 | ✅ | 所有写操作统一 flow |
| failed/stale outbox 重置 pending 清锁重试 | ✅ | reset_outbox（nutri 清 locked_at） |
| published outbox 原样重放 | ✅ | replay_outbox 同 event_id |
| Nutri failed inbox 重放 HM outbox | ✅ | replay_nutri_inbox |
| HM inbox 缺失→重放 capture-ready；存在→克隆任务 | ✅ | replay_hm_inbox 预检（published + 无 inbox + 无任务，否则 409 引导克隆） |
| 克隆任务（保留旧记录/新 queued/独立幂等键/production 或指定 release/原 trace/来源+操作 ID/meal 与图片校验/Nutri 回 analysing） | ✅ | retry + 预览校验报告（clonable/reasons/releases） |
| 恢复超时 attempt：行锁+lock_version；余次重排；耗尽发 failure 事件 | ✅ | 事务内 attempt 行 + 任务行 FOR UPDATE、lock_version 双校验；attempt_no<max_attempts→requeue；否则任务 failed + 标准 nutrition.analysis.failed.v1 outbox（与 Kotlin fail() 结构一致），与 HealthMind 每分钟自动任务互斥不冲突 |
| queued 取消 / 不强制中断 Dify | ✅ | cancel_task |
| 无 SQL 控制台/物理删除/改成功历史 | ✅ | 保持 |
| 一键诊断入口 | ✅ | /api/repair/plan + 修复页；总览滞留表行内“修复”按钮直达 |

## 6. V1.1 补充需求

### A. 观感
- 主题系统：4 基色（midnight/light/slate/olive）+ 6 强调色 + 跟随系统；CSS 变量 token；首屏防闪烁；200ms 颜色过渡；状态脉冲/翻转动画；reduced-motion 降级。
- 长文本/JSON：表格省略号 + 行详情抽屉 + 可折叠 JSON 树（shadow DOM 自定义元素，文本节点渲染防注入）+ 一键复制 + 敏感键掩码提示。
- 键盘可达（Tab/Esc/focus-visible）、响应式（<980px 侧栏折叠顶栏）。

### B. 结构
- 后端：api/（按资源域 router）+ repositories/（overview/tasks/trace/rows/releases/recovery mixin 门面）+ services/（kafka/dify）+ db/ + ui/（page/parts/fmt）+ models/security/audit/util。
- 前端：templates/base + views/* + partials/*；static/css(tokens/theme/base/components/views) + js（main/hx/theme/sse/flow/json-tree/views/*）；无 npm、无 CDN 运行时依赖（hx 属性与官方 htmx 同名，可平滑替换）。
- 清理：删除单文件 app.js/app.css/单页 index.html；移除根 __init__.py；README 只使用父级 .venv。

### C. 数据与运维
- 审计页（本机 JSONL + workflow_release_audits）；版本对比详情；行浏览器动态列；隐藏标签页暂停轮询与 SSE 断线指数退避重连。
- 性能：SSE 只推 status_light；Kafka 元数据 8s 缓存、探活 15s 缓存；列表投影；payload 惰性；keyset 双键。
- 测试：canonical 对照、cursor、redact、审计 tail、JS node --check（全模块递归）、真库冒烟（./tests/_smoke.py 可选）。

## 7. 明确不做（v1）
- Kafka：不建/删 topic、不重置消费组 offset、不改配置。
- 数据：无任意 SQL 控制台、无物理删除、不修改历史成功记录。
- Dify：不读取 difyctl 凭据文件；--include-secret 永不启用；API Key 只走 Nacos/环境变量。
