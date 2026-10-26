# HealthMind Agent Protocol v1

本文件定义 HealthMind 与 NutriAthenaAgent 的 HTTP 身份契约。字段以
`src/main/resources/agent-protocol/v1/` 下的 JSON Schema 和共享示例为准。

## Thread 创建与读取

`POST /threads` 请求：

```json
{
  "thread_id": "<attempt UUID>",
  "metadata": {
    "task_id": "<task UUID>",
    "attempt_id": "<attempt UUID>"
  }
}
```

`POST /threads` 和 `GET /threads/{thread_id}` 必须返回：

```json
{
  "thread_id": "<attempt UUID>",
  "metadata": {
    "task_id": "<task UUID>",
    "attempt_id": "<attempt UUID>"
  }
}
```

`thread_id` 必须等于 `attempt_id`。HealthMind 在启动 run 前校验完整身份；响应缺少
`metadata` 时不会创建 run。

## Run

Run 请求和响应继续遵循 `HealthMind/doc/agent-runtime.md`：

- 输入只有 `task_id`、`attempt_id`、`trace_id`。
- metadata 固定 `task_id`、`attempt_id`、`release_id`、`artifact_sha256`。
- 一个 attempt 最多一个 run。
- 响应丢失后只能通过 list-runs 对账，不能再次 POST。

## 共享夹具

Kotlin 和 Python 测试必须读取同一组资源：

- `thread-create-request.json`
- `thread-response.json`
- `run-create-request.json`
- `run-response.json`

对应 JSON Schema 位于同一目录。修改字段时同时更新 Schema、夹具、两端模型与测试。

