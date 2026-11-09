# Execution 导航

上级入口：[包导航](../AGENTS.md)。

- [ports.py](ports.py) 定义 RunRepository、MealRunner 与 TokenVerifier 结构协议。
- [types.py](types.py) 提供 RuntimeIdentity 与共享 ConflictError。
- [worker.py](worker.py) 提供 DurableWorker：维护清理、领取、身份复核、心跳与取消/超时、条件终态写入。
- PostgreSQL 适配器：[storage](../storage/AGENTS.md)。
- 测试入口：[execution 测试](../../../tests/execution/AGENTS.md)。

[service.py](service.py) 协调 thread/run 提交、对账、等待和取消，使用 [types.py](types.py) 的传输无关命令与错误；HTTP 响应转换在 API 层。
