# Storage 导航

上级入口：[包导航](../AGENTS.md)。

- [postgres.py](postgres.py) 导出 Repository；[__init__.py](__init__.py) 提供包入口与共享 ConflictError。
- [pool.py](pool.py) 管理连接池、行查询和 schema 就绪检查。
- [threads.py](threads.py) 维护 attempt 绑定的线程身份。
- [runs.py](runs.py) 负责提交幂等、查询和取消请求。
- [leases.py](leases.py) 负责四项身份过滤、续租、失联中断与终态 fencing。
- [retention.py](retention.py) 负责结果过期和 run/thread 清理。
- [migrations.py](migrations.py) 负责迁移账本及校验；SQL 位置由 runtime.paths.MIGRATIONS_ROOT 提供。
- 测试入口：[storage 测试](../../../tests/storage/AGENTS.md)。
