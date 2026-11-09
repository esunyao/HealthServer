# Python 包导航

上级：[src 导航](../AGENTS.md) · [模块导航](../../AGENTS.md)。

[main.py](main.py) 只保留稳定启动入口；下列目录各自维护实现导航。

| 职责 | 内容 |
|---|---|
| [cli](cli/AGENTS.md) | 命令参数、分派与 smoke |
| [runtime](runtime/AGENTS.md) | 组件装配、生命周期、路径与制品 |
| [config](config/AGENTS.md) | 类型化配置与兼容加载 |
| [api](api/AGENTS.md) | HTTP 路由、依赖与响应模型 |
| [execution](execution/AGENTS.md) | run 协调服务、worker 与注入协议 |
| [storage](storage/AGENTS.md) | PostgreSQL 事务、租约与迁移 |
| [integrations](integrations/AGENTS.md) | JWT、模型、图像与只读 MCP |
| [meal](meal/AGENTS.md) | 餐食工具循环、提示词与结果契约 |
| [observability](observability/AGENTS.md) | 日志、脱敏、异常与执行轨迹 |
| [examples](examples/AGENTS.md) | 离线图与最小模型示例 |

阅读顺序：先看目标职责导航，再看它引用的少量文件与测试。依赖由 runtime 装配；execution 通过 ports 依赖存储与餐食 runner，API 通过 service 协调执行。低层组件不反向导入 API、CLI 或 bootstrap。
