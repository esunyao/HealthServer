# NutriMemo tests

上级规范与导航：[根 AGENTS.md](../../../AGENTS.md) · [模块 AGENTS.md](../../AGENTS.md) · [公开说明](../doc/README.md)

本目录只负责测试导航：

- `integration/` 覆盖结果消费、completed/failed/review-required、报告幂等与人工修正保护。
- `contract/` 验证 OpenAPI 路径和公开响应模型；公开字段变化必须同步 `NutriMemo/openapi.yaml`。
- `config/` 验证迁移文件名和 SQL 约束；数据库行为需要在可用 PostgreSQL 环境验证。
- 不读取真实 `.env`，不打印用户健康数据、签名 URL 或真实餐食内容。

