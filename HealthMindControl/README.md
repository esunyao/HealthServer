# HealthMindControl

仅监听本机的 HealthMind 运维控制台。它直接读取 PostgreSQL 和 Kafka；所有写操作都要求先预览、填写原因并再次确认。

```bash
uv sync --project HealthMindControl --active --extra test
uv run --project HealthMindControl healthmind-control
```

复制 `.env.example` 为 `.env` 并填写连接信息，然后访问 <http://127.0.0.1:8765>。不要提交 `.env`。

主要页面包括总览、任务与链路、Kafka、Dify 版本和 inbox/outbox 修复。Kafka 查看消费者从不提交 offset。Dify App API Key 仍由 HealthMind 的 Nacos/环境变量管理。

