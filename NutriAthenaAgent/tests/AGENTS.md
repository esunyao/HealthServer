# 测试导航

上级：[模块导航](../AGENTS.md) · [源码职责](../src/nutriathena_agent/AGENTS.md)。[conftest.py](conftest.py) 隔离 loguru 和 stdlib 全局状态。

| 目录 | 关注点 |
|---|---|
| [contract](contract/AGENTS.md) | 共享 HTTP 夹具、提示词/结果 Schema 基线 |
| [runtime](runtime/AGENTS.md) | 资源生命周期和制品摘要 |
| [config](config/AGENTS.md) | 变量兼容、边界与凭据表示 |
| [cli](cli/AGENTS.md) | 命令默认值、smoke 对账 |
| [execution](execution/AGENTS.md) | worker 租约、终态和取消 |
| [storage](storage/AGENTS.md) | 迁移校验、仓储协议与隔离 PostgreSQL |
| [integrations](integrations/AGENTS.md) | JWT、图像、MCP 与模型装配 |
| [meal](meal/AGENTS.md) | 真实假模型循环、图像/备注/工具/输出 |
| [observability](observability/AGENTS.md) | 日志格式、颜色、脱敏、异常、回调和并发上下文 |
| [examples](examples/AGENTS.md) | 离线图及最小 agent |

离线执行：`PYTHON_DOTENV_DISABLED=1 uv run pytest -q -m "not integration"`。数据库验证：`uv run pytest -q -m integration`，仅使用临时 PostgreSQL 容器。夹具直接读取仓库 integration-contracts，目录变更时以模块根定位，不能复制为另一份契约。
