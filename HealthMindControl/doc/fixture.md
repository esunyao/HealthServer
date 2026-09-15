# 数据构造与 MCP 手动测试

## 最短测试链路

```text
已有 AI 任务
    │ 选择为模板
    ▼
HealthMindControl ──事务写入──► ai_tasks(running)
    │                           ai_task_attempts(running)
    │
    └──复制 task_id / attempt_id / trace_id
                                │
                                ▼
                         Dify 草稿测试
                                │
                                ▼
                         HealthMind MCP
                                │
                                ▼
                       ai_tool_invocations
```

该路径不经过 Nutri outbox、Kafka 或 HealthMind 任务调度器。源任务及 Nutri 餐食状态均不修改。
测试 task 沿用源任务的 workflow release，因此 MCP 仍能按正式的工具绑定、scope、调用次数和
请求 schema 进行授权。

## 数据构造器

高级模式从现有 task、attempt、event、meal 或 trace 定位任务链，将字段设置为继承、关联、
自动生成或手动输入，再写入选定的运行期白名单表。预览会在回滚事务中实际执行一次 SQL，
因此外键、唯一约束、状态约束和必填字段会在正式写入前暴露。

outbox 的推荐模板默认保持到 2099，不会被发布器领取。只有操作者单独预览并确认“放行”后，
`next_attempt_at` 才恢复为当前时间。

## 生命周期

MCP 测试 attempt 的数据库超时为一小时，HMC 租期默认 50 分钟。可以续期，也可以主动结束；
结束只把测试 task/attempt 标为 cancelled，不删除记录、不生成业务 outbox。到期扫描执行同样的
关闭操作，避免 HealthMind 将测试 attempt 当作正式超时任务恢复。
