# Storage 测试导航

上级入口：[测试导航](../AGENTS.md)。

- [test_migration_checksums.py](test_migration_checksums.py) 验证历史 LF/CRLF 校验互认和篡改拒绝。
- [test_repository_contract.py](test_repository_contract.py) 离线验证端口调用签名、共享冲突类型和连接池注入。
- [test_postgres_runtime.py](test_postgres_runtime.py) 验证独立 PostgreSQL 容器中的迁移、幂等、身份过滤、fencing、取消和保留清理。
- 迁移资源路径由 runtime.paths.MIGRATIONS_ROOT 提供，与测试目录层级无关。
- 实现入口：[storage](../../src/nutriathena_agent/storage/AGENTS.md)。
