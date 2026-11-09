# 运行装配导航

上级：[包导航](../AGENTS.md)。公开说明：[模块契约](../../../doc/README.md)。

[bootstrap.py](bootstrap.py) 只构造组件，[lifecycle.py](lifecycle.py) 管理资源所有权、启动失败和关闭；[paths.py](paths.py) 从包锚点解析路径；[artifact.py](artifact.py) 计算制品身份；[migration.py](migration.py) 是显式迁移命令。

对应验证：[测试导航](../../../tests/AGENTS.md)。
