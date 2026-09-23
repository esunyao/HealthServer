# AgentDevelop

AgentDevelop 当前包含两段 LangGraph 教学样板，以及一个**手动运行的餐食分析 DeepAgent 原型**。原型用于在替换 Dify 前验证模型、图片、MCP 上下文和结果契约；它不会自动接收 HealthMind 任务，也不承担生产编排。

本阶段只实现 Agent 客户端：不修改 HealthMind、NutriMemo、Orion、Kafka、MCP 工具或数据库；Agent 本身不调用 Dify、不写业务数据、不发布 Kafka 消息。

AI 导航入口见 [`AGENTS.md`](./AGENTS.md)（代码地图、配置与边界）。

## 功能

| 功能 | 命令/文件 | 作用 |
|---|---|---|
| 离线图示例 | `agentdevelop graph` | 学习 `StateGraph`、状态、reducer、条件边与流式执行 |
| 最小 Agent 示例 | `agentdevelop agent` | 学习 `create_agent` 与自定义工具 |
| 餐食分析 Agent | `agentdevelop meal` / [`meal_agent.py`](./src/agentdevelop/meal_agent.py) | 读取本地图片和知识证据，连接现有 HealthMind MCP，输出经本地契约校验的 JSON |

## 跑起来

```bash
cd AgentDevelop

# 安装（含测试依赖）
uv sync --extra test

# ① 纯图，不需要任何凭据
uv run agentdevelop graph
uv run agentdevelop graph "嗯"        # 换输入：太短会走 reject 分支

# 测试（不需要外部服务或真实 API Key）
uv run pytest -q

# 完成配置后，手动运行餐食分析；每张图片使用一个 --image
uv run agentdevelop meal --task-id 11111111-1111-4111-8111-111111111111 --attempt-id 22222222-2222-4222-8222-222222222222 --image ".\meal-1.jpg" --evidence ".\knowledge-evidence.json" --note "米饭吃完，鱼只吃了一半"
uv run agentdevelop meal --help
```

餐食结果 JSON 写到标准输出，诊断信息写到标准错误。`needs_review` 是正常的分析结果，不代表程序崩溃。

`task_id` / `attempt_id` 必须是 HealthMind 已授权的任务与 attempt UUID；建议从 HealthMindControl 的“MCP 测试”会话取得。Agent 不创建或修改这些记录。测试前确认相应 workflow release 已绑定 `nutrimemo.capture_context.get` 和 `orion.nutrition_context.get`。

## 配置

复制模板并填写：

```bash
Copy-Item .env.example .env
```

| 变量 | 必填 | 说明 |
|---|---|---|
| `AGENTDEVELOP_API_KEY` | 是 | OpenAI 兼容模型 API Key；不写入命令或输出 |
| `AGENTDEVELOP_BASE_URL` | 是 | 模型兼容端点地址 |
| `AGENTDEVELOP_MODEL` | 否 | 教学 Agent 使用，默认 `deepseek-chat` |
| `AGENTDEVELOP_MEAL_MODEL` | 是（meal） | 必须是支持视觉输入的模型；不自动回退到纯文本模型 |
| `AGENTDEVELOP_MCP_URL` | 是（meal） | HealthMind Streamable HTTP MCP 地址，默认示例为 `http://localhost:8100/mcp` |
| `AGENTDEVELOP_OAUTH_TOKEN_URL` | 是（meal） | Authentik OAuth token endpoint，模板为本地开发地址 |
| `AGENTDEVELOP_OAUTH_CLIENT_ID` | 是（meal） | 必须与 HealthMind 的 `allowed-dify-client-id` 相同，默认 `dify-healthmind` |
| `AGENTDEVELOP_OAUTH_CLIENT_SECRET` | 是（meal） | 已获准的 Dify/HealthMind MCP OAuth client secret |
| `AGENTDEVELOP_MCP_SCOPES` | 否 | 默认请求 capture-context 与 nutrition-context 两个只读 scope |

`AGENTDEVELOP_MEAL_MODEL` 要选择支持图像输入的模型；示例中的 `deepseek-chat` 是教学 Agent 默认值，不保证能看图。OAuth access token 使用 client-credentials 获取，不传入模型，也不会打印到终端。Authentik 必须为该客户端签发 `aud=healthmind-mcp`，并授予上表中的两个 scope；HealthMind 还会校验允许的 client ID、任务、attempt、工具绑定和调用次数。OAuth 请求超时为 15 秒，MCP 请求超时为 20 秒。若本地服务不在示例地址，请按实际部署修改 MCP/token URL。

然后可继续运行教学 Agent：

```bash
uv run agentdevelop agent
uv run agentdevelop agent "统计一下这句话的词数：晚饭吃了清蒸鲈鱼"
```

`.env` 不在版本控制内；已在 shell 中导出的同名环境变量优先于 `.env`。

## 餐食输入与边界

- 用一个或多个 `--image` 提供本机 JPEG、PNG 或 WebP 文件；顺序保持不变。默认上限为 10 张、每张 10 MiB、合计 100 MiB。
- `--evidence` 接收知识库已检索的 JSON（对象或数组，最多 1 MiB）。第一阶段不迁移或自动查询 Dify 知识库。
- Agent 通过现有 MCP 工具读取餐食元数据和已授权的最小营养上下文；task/attempt ID 在 MCP 调用端注入，不暴露为模型可填写参数。
- Capture MCP 返回的签名图片 URL 会从模型上下文中删除。图像只使用本地 `--image` 文件，不由 Agent 下载 MCP URL。
- 只开放两个只读 MCP 工具；DeepAgents 的文件系统、shell、删除和子 Agent 工具对模型禁用。
- 最终输出是 HealthMind 兼容成功对象或 `needs_review` 对象；Agent 不会自动把结果写回 HealthMind/NutriMemo。

## 依赖

Python 3.11，使用 `uv` 管理。餐食 Agent 由 `deepagents`、`langchain-openai` 和 `langchain-mcp-adapters` 提供；测试不会连接外部模型、MCP、数据库或 Kafka。
