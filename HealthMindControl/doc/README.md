# HealthMindControl — 模块大体说明

HealthMind 的本地运维控制台，默认监听 `127.0.0.1:8765`。它通过 FastAPI、Jinja2 和原生 ES modules 提供诊断、任务、Kafka、Dify Workflow Release 与审计视图。

运行时依赖由 `.env` 注入；公开模板只提供不可连接的占位符。Python 版本范围是 `>=3.12,<3.13`。

## 主要边界

- 只面向本机运维，不作为公网管理 API。
- 写操作采用预览、确认令牌、执行和审计链路。
- 数据库写入与本地 JSONL 审计分别记录操作结果。
- 不提供任意 SQL、Kafka topic/offset 管理、物理删除或历史成功记录修改。

## 代码结构

- `api/`：页面和诊断 API。
- `services/`：Kafka、Dify 和业务动作服务。
- `repositories/`、`db/`：数据库访问和连接管理。
- `ui/`、`static/`、`templates/`：页面、样式、脚本和模板。
- `config.py`：`HMC_*` 环境配置；外部 Kafka、Dify、MCP、Authentik 地址无仓库默认值。

## 合规状态

公开合规摘要见 [requirements.md](./requirements.md)。当前状态包含已验证、已复现缺陷和未验证场景，不能将“代码路径存在”理解为通过集成、并发或真实外部系统验收。维护者的本地详细核查记录不属于公开文档依赖。

## 验证

```powershell
Set-Location HealthMindControl
python -m pytest -q
```

真实 PostgreSQL、Kafka、Dify 和 MCP 连接测试需要本地 `.env` 与相应权限；不要把实际地址或凭据写入仓库。