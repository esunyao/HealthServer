# HealthMind ↔ 自托管 LangGraph 运行端契约

本文件定义下一阶段 AgentDevelop 必须实现的 HTTP 契约。本阶段仅实现 HealthMind 客户端；尚无真实运行端，不能据此宣称端到端可用。运行端使用 LangGraph 构建图，但 HTTP 生命周期遵循 Agent Protocol 的后台 run 模式，并增加必须实现的幂等与版本校验约束。

## 调用与授权

HealthMind 使用 Authentik `client_credentials` 获取短期 Bearer token，调用 Agent 运行端。运行端必须验证签名、issuer、`aud=healthmind-agent`、`azp/client_id=healthmind-agent` 与 `healthmind.agent.run` scope。调用使用 HTTPS；仅 loopback 开发测试可用 HTTP。密钥只在环境或 Nacos，不能入库、日志或 Git。

Agent 回调 HealthMind MCP 时使用独立的服务身份 `langgraph-healthmind`，token 必须含 `aud=healthmind-mcp` 与相应工具 scope。Agent 只能把 `task_id`、`attempt_id` 传给工具；图片及授权上下文由 MCP 按任务读取。HealthMind 向运行端的输入只有 `task_id`、`attempt_id`、`trace_id`，不传用户画像、图片 URL 或文件字节。

## HTTP 生命周期

| 操作 | 请求/响应要求 |
|---|---|
| `POST /runs` | 请求含 `assistant_id`、上述三个 `input` ID、`metadata.task_id/attempt_id/release_id/artifact_sha256`、`on_completion=keep`，并带 `Idempotency-Key: <attempt_id>`。响应含 UUID `run_id`、`assistant_id` 与同一组 metadata。 |
| `GET /runs/{run_id}` | 响应含相同 `run_id`、`assistant_id`、metadata 与 `status`：`pending`、`running`、`success`、`error` 或 `interrupted`。 |
| `GET /runs/{run_id}/wait` | 仅在 `success` 后调用，响应为 `{"output": <餐食结果对象>}`；结果须可在运行结束后至少保留 24 小时，供断线恢复。 |
| `POST /runs/{run_id}/cancel` | attempt 超时时尽力取消远端运行；取消响应丢失不改变 HealthMind 已持久化的超时状态。 |

`POST /runs` 的幂等键是**强制扩展契约**：同一 attempt 重复提交，必须返回同一个 run 与相同 metadata，不能再启动一份图；同键不同请求必须拒绝。HealthMind 在响应丢失后会原样重试，不能接入未验证该语义的运行端。run 的 `artifact_sha256` 必须来自运行端实际加载的部署制品，而不是盲目回显请求；不匹配时 HealthMind 拒绝结果。部署 key 在 release 生命周期内不得重新指向其他制品。

现有 `workflow_releases.input_schema` 校验的是进入 HealthMind 的 Kafka capture-ready 事件，不是 `/runs` 的三 ID 请求；`output_schema` 校验 Agent 最终营养结果。两种输入契约不能混用。

成功 `output` 是符合当前 release `output_schema` 的裸 JSON 对象（例如 `overall_confidence` 与 `items`），没有 `result`、`decision` 或 Markdown 包装。若 Agent 无法可靠分析，可输出 `{"status":"needs_review","reason_code":"...","message":"..."}`；HealthMind 将其转为失败事件，不写成功营养结果。HealthMind 在数据库事务内写 attempt、结果、任务与 outbox；Kafka 事件格式不变。

运行中任务受 `HEALTHMIND_AGENT_MAX_IN_FLIGHT` 限流；仅 HealthMind 自己创建且标记 `agent_managed=true` 的 attempt 进入提交、轮询和超时恢复，手工 MCP 调试 attempt 默认不被后台接管。Agent 请求使用数据库租约避免多实例在一次 HTTP 调用期间重复领取同一 attempt。调度线程池默认 4 线程，使远端调用不阻塞 outbox 与超时恢复。租约到期后仍可能重试启动请求，因此运行端的 `Idempotency-Key` 语义不可省略。

## 版本登记与切换

Flyway V4 在停机维护窗口运行，清空 HealthMind 旧运行记录并删除旧提供方字段，**不清除**任务类型或 MCP 工具定义，也不修改 NutriMemo 或 Kafka 消费位点。先备份 `healthmind` schema，再启动新版应用完成迁移。旧的已消费事件不会自动重放。

使用 `db/manual/register_agent_release.sql` 以 `psql -v` 提供 `release_id`、`release_version`、`deployment_key`、`assistant_id`、实际制品的 `artifact_sha256`、`input_schema_version`、`input_schema`、`input_schema_sha256`、`output_schema_version`、`output_schema`、`output_schema_sha256`、`timeout_seconds`、`max_attempts`、`actor_id`、`reason` 和 `trace_id`。Schema 哈希按 HealthMind `CanonicalJson` 的排序 JSON 计算。脚本登记 candidate 并绑定两项 MCP 工具；经部署与契约验证后，使用 `promote_workflow_release.sql` 提升为 production。提升后 release 身份、契约和工具绑定均不可修改。生产 release 固定在任务创建时，重试不切换版本。新的部署必须使用新的 deployment key；从配置或 Nacos 提供该 key 到 HTTPS URL 的映射，随后重启 HealthMind 使客户端映射生效。

HMC 的当前版本页面和部分数据构造 SQL 仍使用旧模型，本阶段禁止修改 HMC，因此不能用它登记或提升 Agent release；数据构造等功能需在后续适配时重新验收。即使 HMC 能创建手工 running attempt，HealthMind 也不会接管其运行。
