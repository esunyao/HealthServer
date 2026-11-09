# HTTP 路由导航

上级：[API 导航](../AGENTS.md)。

[health.py](health.py) 是匿名数据库探针；[thread.py](thread.py) 是 attempt-bound thread；[run.py](run.py) 是提交、对账、状态、等待与取消。鉴权在上级 dependencies，业务校验与事务协调在 execution/service.py，响应转换在上级 schemas。
