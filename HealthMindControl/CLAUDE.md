# CLAUDE.md — HealthMindControl

本地运维控制台（FastAPI + Jinja2 + 原生 ES modules，127.0.0.1:8765，Python ≥3.12）。

## 结构速览
- 入口 src/healthmind_control/main.py（uvicorn，Windows Selector loop）；app.py 只做装配：
  lifespan 注入 app.state.{csrf_token, previews, audit, db, repo, kafka, dify}，模板全局
  fmt_ts/col_label/badge_cls 在 app.py 注册。
- 领域查询在 repositories/：OverviewMixin/TasksMixin/RowsMixin/TraceMixin/ReleasesMixin/RecoveryMixin，
  门面 Repository 单例。禁止在代码里直接拼表名；行浏览器必须走 rows.py 的 ROW_KINDS allowlist
  （新表先登记 kind）。
- 写操作模式：api 路由 → preview（require_csrf + 快照）→ 客户端输入确认文本 → execute
  （previews.consume 单次 + sha256 快照比对）→ repo 事务 → audit.write。新写操作一律照抄，禁止绕过 PreviewStore。
- 敏感数据：响应出口统一 redact()（security.py）；预签名 URL 参数截断。
- Kafka：诊断只读（临时组、auto.commit/store=false、隐藏 healthmind-control-* 组）；生产只走受控流。
- 前端无构建：static/js/hx.js 实现 htmx 子集（hx-get/trigger/target/swap/include/indicator/push-url），
  新片段保持 hx-* 属性风格；JSON 长内容一律抽屉 + js/json-tree.js；时间单元格 data-ts 客户端本地化。
- 主题：CSS 变量（tokens.css 基色 + 强调色），html[data-theme]/[data-accent]，localStorage hmc.theme；
  新增颜色必须走变量，禁止散落十六进制。
- 对照测试：HealthMind Kotlin CanonicalJson 与 security.sha256_json 一致性由
  tests/test_canonical_parity.py 重算 V2 seed 哈希保障——schema/事件结构改动时同步更新对照。

## 常用命令（仓库根执行）
- pytest: .venv\Scripts\python.exe -m pytest -q HealthMindControl\tests
- 冒烟（真库）: .venv\Scripts\python.exe HealthMindControl\tests\_smoke.py
- 启动: cd HealthMindControl && uv run --active --project . healthmind-control

## 规则
- 不开放非 127.0.0.1 监听；不引入需要构建的运行时依赖；不把 .env/审计/凭据提交 git。
- HealthMind/NutriMemo schema 只读消费；确需改库走对应模块 Flyway migration 并同步 requirements.md。
- 每次变更同时写 workflow_release_audits（新 action 先扩 HealthMind V3 的 CHECK 名单）与本地 JSONL。