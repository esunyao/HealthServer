# 配置导航

上级：[包导航](../AGENTS.md)。公开说明：[模块契约](../../../doc/README.md)。

[models.py](models.py) 为组件传入的不可变值；[loader.py](loader.py) 用 Pydantic Settings 校验环境并保留新旧别名、空值和 debug 语义。环境合并使用 python-dotenv，生产变量范围只在加载边界校验。

对应验证：[测试导航](../../../tests/AGENTS.md)。
