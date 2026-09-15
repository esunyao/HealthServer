# HealthMindControl 合规状态摘要

> 本页是公开摘要，不替代维护者本地的详细核查材料；本页不复制私有核查内容。

## 状态含义

- `✅ 已验证`：代码路径存在，并有当前单测或定点证据。
- `⚠️ 已复现缺陷`：已有明确复现或代码证据，不能按完成项使用。
- `❓ 未验证`：缺少真实数据库、Kafka、Dify、浏览器或并发环境证据。

## 当前结论

- ✅ v0.3 的服务端预览意图绑定、单次令牌、CSRF、审计、Kafka 原始 JSON 投递和 JavaScript BIGINT 无损响应已有单元测试。
- ✅ Windows Selector 事件循环保留；`difyctl` 改由工作线程执行，不再依赖不兼容的 asyncio 子进程实现。
- ✅ Kafka 诊断消费者使用 librdkafka 的点号配置键，且 auto commit/store 均关闭。
- ✅ 本机真实配置下，PostgreSQL、Kafka 元数据/消费组和现有只读 Web API 已完成冒烟；实验台经过浏览器渲染检查。
- ✅ 克隆任务校验 release/task type、同餐食活动任务与稳定幂等键；attempt 恢复要求最新 attempt 和服务端锁版本；取消 queued 任务会产生下游失败事件。
- ✅ 专家 SQL 使用 PostgreSQL parser 限定单语句，预览强制回滚；消费组 offset 仅允许无在线成员时变更。两者默认关闭。
- ⚠️ 真实生产数据库的写操作、Dify/MCP 直调、Kafka offset 变更以及故障注入不会由自动测试执行，必须由操作者在实验台逐步预览后验收。
- ❓ Redpanda/Testcontainers 并发集成套件和全链路自动化浏览器写操作尚未加入持续集成。

本公开摘要不等于生产就绪声明；危险操作仍以页面预览、当前快照、确认文本和审计记录为准。
