# Execution 导航

上级入口：[包导航](../AGENTS.md)。

- [ports.py](ports.py) 定义 RunRepository、MealRunner 与 TokenVerifier 结构协议。
- [types.py](types.py) 提供 RuntimeIdentity 与共享 ConflictError。
- [worker.py](worker.py) 提供 DurableWorker：维护清理、领取、身份复核、心跳与取消/超时、条件终态写入。
- PostgreSQL 适配器：[storage](../storage/AGENTS.md)。
- 测试入口：[execution 测试](../../../tests/execution/AGENTS.md)。
