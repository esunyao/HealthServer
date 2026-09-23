# AgentDevelop — AI 工作指南（导航）

> 本文件只做导航与理解，不新增规范；规范来源是根 [`AGENTS.md`](../AGENTS.md) 与 [`README.md`](./README.md)。行为与技术结论以源码、[`pyproject.toml`](./pyproject.toml)、`uv.lock` 与测试为准。本文件不复制规范、不维护第二套规则。

## 这个目录是什么

**独立餐食分析 Agent 原型**：本目录保留两段 LangGraph 教学示例，并增加一个由 CLI 手动运行的 DeepAgent，用于在替换 Dify 前验证图片输入、HealthMind MCP 读取与结果契约。它不是可部署服务，也没有接入自动任务链路。

边界：
- owns：两段教学样板、独立餐食分析 DeepAgent、只读 HealthMind MCP 客户端、本目录的工程与文档。
- not owns：生产 AI 编排、任务创建/修复、数据库写入、Kafka 发布、Dify 调用或任何服务端 MCP 逻辑。

> [!important]
> 本阶段仅构建并手动运行 Agent。HealthMind、NutriMemo、Orion、MCP 工具与业务契约均不修改；Agent 不自动接收线上任务，也不会自动写回分析结果。

## 快速事实

| 项 | 值 |
|---|---|
| 类型 | 非 Gradle 模块；Python `>=3.11`，uv 管理（[`pyproject.toml`](./pyproject.toml)、`uv.lock`）；构建后端 `uv_build`，`src/` 布局 |
| 入口 | [`src/agentdevelop/main.py`](./src/agentdevelop/main.py)：`graph`、`agent`、`meal` 子命令 |
| 依赖 | LangGraph、`deepagents`、LangChain OpenAI、`langchain-mcp-adapters`、httpx、Pydantic；测试依赖在 `test` extra |
| 配置 | 模块自己的 `.env`（模板见 [`.env.example`](./.env.example)；AI 不读实际 `.env` 内容）；变量全部 `AGENTDEVELOP_*` 前缀 |
| 文档 | 本文件 + [`README.md`](./README.md)（运行手册）。**无 `doc/` 目录**，按根 `AGENTS.md` 的约定以本地说明文件为准 |

## 代码地图

| 位置 | 职责 |
|---|---|
| [`src/agentdevelop/basic_graph.py`](./src/agentdevelop/basic_graph.py) | **① 纯图**：`StateGraph`、`TypedDict` 状态、`operator.add` reducer、条件边、`stream`/`invoke`。不调用模型，离线可跑 |
| [`src/agentdevelop/simple_agent.py`](./src/agentdevelop/simple_agent.py) | **② 最小 agent**：`create_agent` + `@tool` 自定义工具，打印消息轨迹让工具循环可见 |
| [`src/agentdevelop/meal_agent.py`](./src/agentdevelop/meal_agent.py) | 手动餐食 Agent：传入图片/证据，连接授权 MCP 读取，并在本地校验输出 |
| [`src/agentdevelop/mcp_tools.py`](./src/agentdevelop/mcp_tools.py) | Authentik client-credentials 与两个允许的 HealthMind MCP 只读工具封装；服务端 IDs 由 CLI 注入 |
| [`src/agentdevelop/images.py`](./src/agentdevelop/images.py) | 本地图片格式、张数和大小校验，以及多模态消息编码 |
| [`src/agentdevelop/contracts.py`](./src/agentdevelop/contracts.py) | Pydantic 成功/`needs_review` 结果契约校验 |
| [`src/agentdevelop/dietary_prompt.py`](./src/agentdevelop/dietary_prompt.py) | 只读装载 [`../AgentDeveloper/skills`](../AgentDeveloper/skills) 中的现有餐食、纤维和结果契约规范 |
| [`src/agentdevelop/config.py`](./src/agentdevelop/config.py) | 教学模型与视觉餐食模型分别配置，读取模块 `.env` |
| [`src/agentdevelop/main.py`](./src/agentdevelop/main.py) | `graph` / `agent` / `meal` 命令；无参数默认运行离线图示例 |
| [`tests/`](./tests/) | 离线单元测试；不连接真实 API Key、OAuth、MCP、PostgreSQL 或 Kafka |

## 任务 → 读什么

| 你要做的事 | 先读 |
|---|---|
| 搞懂 LangGraph 图怎么搭 | [`basic_graph.py`](./src/agentdevelop/basic_graph.py) |
| 搞懂最小 agent 循环 | [`simple_agent.py`](./src/agentdevelop/simple_agent.py) |
| 手动跑餐食 Agent | [`README.md`](./README.md) 的“餐食输入与边界”与“配置” + [`meal_agent.py`](./src/agentdevelop/meal_agent.py) |
| 调整视觉模型或 MCP 地址 | [`config.py`](./src/agentdevelop/config.py) + [`.env.example`](./.env.example)；实际凭据留在本机 `.env` |
| 调整成功/复核结果契约 | [`contracts.py`](./src/agentdevelop/contracts.py) + [`AgentDeveloper/skills/diet-result-contract`](../AgentDeveloper/skills/diet-result-contract/SKILL.md) |
| 让 Agent 接入 HealthMind 生产链路 | **本阶段不做**：这需要单独设计并修改服务端；先阅读 [../HealthMind/AGENTS.md](../HealthMind/AGENTS.md)、[../integration-contracts/AGENTS.md](../integration-contracts/AGENTS.md) 与 [../HealthMindControl/doc/analysis-chain.md](../HealthMindControl/doc/analysis-chain.md) |

## 关键事实与易错点

- **餐食 Agent 只手动运行**：没有任务轮询、Kafka 消费、业务数据库连接、结果回写或生产部署。
- **本地图片才是视觉输入**：`meal` 只接收命令行提供的 JPEG/PNG/WebP 文件；不会尝试下载 capture MCP 返回的预签名 URL。
- **MCP 只读且最小化**：只暴露 `nutrimemo.capture_context.get` 和 `orion.nutrition_context.get`。Wrapper 固定注入 task/attempt IDs，过滤签名 URL 和不需要回显的业务 ID，并限制每个工具每次运行至多调用一次。
- **OAuth 由操作者配置**：手动运行者需配置与 HealthMind allowlist 匹配的 client ID、secret、audience 和只读 scopes；token 不进入模型 prompt 或终端输出。
- **DeepAgents 内建能力受限**：通过模型 profile 禁用文件系统、shell、删除和 subagent 工具；模型不能在本机执行任意命令或修改文件。
- **知识库暂由调用方提供**：`--evidence` 传入已检索 JSON；第一阶段不连接 Dify，也不自行迁移知识库。
- **`create_react_agent` 已废弃**：`langgraph.prebuilt.create_react_agent` 官方标注废弃，新代码用 `langchain.agents.create_agent`（本目录用的是后者）。
- **环境变量用 `AGENTDEVELOP_*` 前缀**，不是 `OPENAI_*`：避免与机器上其他项目的全局 `OPENAI_API_KEY` 串味。`load_dotenv(override=False)`，已导出的真实环境变量优先。
- **视觉模型单独指定**：教学 agent 的 `AGENTDEVELOP_MODEL` 默认 `deepseek-chat`；餐食 Agent 必须显式配置支持图像输入的 `AGENTDEVELOP_MEAL_MODEL`。
- **`graph` 不需要任何凭据**；`agent` 需要模型凭据；`meal` 需要视觉模型、Authentik 和 HealthMind MCP 配置。
- **`.env` 不入库**：真实 key 只放在本地 `.env`（见 [`.gitignore`](./.gitignore)），模板 `.env.example` 里的地址是公开端点、不含凭据。
- **`[project.scripts]` 指向 `agentdevelop.main:main`**（不是 `agentdevelop:main`）：让 `__init__.py` 保持干净，避免包初始化与入口互相 import。

## 测试与验证

```bash
uv sync --extra test
uv run agentdevelop graph        # ① 离线纯图：应逐步打印每个节点
uv run agentdevelop graph "嗯"   # 换输入：应走 reject 分支
uv run pytest -q                 # 所有自动化测试均离线
```

餐食 Agent 的自动化测试覆盖结果契约、图片检查、MCP 参数绑定和敏感字段移除；不需要真实服务。人工 smoke test 需要 HealthMind/Authentik、有效任务和 attempt、模型 API Key、本地图片与 evidence JSON：

```bash
uv run agentdevelop meal --task-id <task-uuid> --attempt-id <attempt-uuid> --image <local-image.jpg> --evidence <evidence.json>
```

最小 agent 教学样例需要真实凭据，不由自动测试执行；配置好 `.env` 后手动运行：

```bash
uv run agentdevelop agent "统计一下这句话的词数：晚饭吃了清蒸鲈鱼"
```

- 测试在 [`tests/`](./tests/)：不连接真实服务。
- 改动 `basic_graph.py` 的状态结构或分支条件时，同步补/改测试。

## 相关文档

- [README.md](./README.md) — 运行手册（两段样板的跑法、`.env` 变量表）。
- [../AGENTS.md](../AGENTS.md) — 仓库规范、阅读导航与项目背景。
- [../HealthMind/AGENTS.md](../HealthMind/AGENTS.md) — 当前承担 AI 编排的模块（Dify 调用方）。
- [../AgentDeveloper/AGENTS.md](../AgentDeveloper/AGENTS.md) — **另一个目录，勿混淆**：那是已提交的 Dify 提示词技能资产，与本目录（Python/LangGraph）没有代码关系。
- [../HealthMindControl/doc/analysis-chain.md](../HealthMindControl/doc/analysis-chain.md) — AI 分析链路现状与排障。
- 私有：`doc-project/`（项目背景，不提交）；本目录无 `docp/`。
