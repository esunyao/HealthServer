# AgentDevelop — AI 工作指南（导航）

> 本文件只做导航与理解，不新增规范；规范来源是根 [`AGENTS.md`](../AGENTS.md) 与 [`README.md`](./README.md)。行为与技术结论以源码、[`pyproject.toml`](./pyproject.toml)、`uv.lock` 与测试为准。本文件不复制规范、不维护第二套规则。

## 这个目录是什么

**LangGraph 学习样板**：两段从零读懂的最小示例，用来先掌握 LangGraph 的组织方式（状态、节点、边、agent 循环），再谈怎么承接真实链路。**当前不是可部署服务，也不是任何链路的运行组件。**

边界：
- owns：两段教学样板（纯图 / 最小 agent）、模型工厂、本目录的工程与文档。
- not owns：AI 分析链路的任何运行时职责。**尚未**接入 HealthMind，**没有**替代 Dify 当前的运行时位置；不碰 Kafka、MCP、结果契约与数据库。

> [!important]
> 长期意图是用自建 agent 承担 Dify 现在的角色，但**那是尚未开始的设计**，本目录里没有它的实现。
> 不要据本目录推断链路行为，也不要把它当成已生效的架构。

## 快速事实

| 项 | 值 |
|---|---|
| 类型 | 非 Gradle 模块；Python `>=3.11`，uv 管理（[`pyproject.toml`](./pyproject.toml)、`uv.lock`）；构建后端 `uv_build`，`src/` 布局 |
| 入口 | [`src/agentdevelop/main.py`](./src/agentdevelop/main.py)（console script `agentdevelop`） |
| 依赖 | `deepagents==0.7.17`、`langchain==1.4.2`、`langchain-openai>=1.6.3`、`langgraph==1.2.12`、`python-dotenv>=1.2.3`；测试依赖在 `test` extra（pytest） |
| 配置 | 模块自己的 `.env`（模板见 [`.env.example`](./.env.example)；AI 不读实际 `.env` 内容）；变量全部 `AGENTDEVELOP_*` 前缀 |
| 文档 | 本文件 + [`README.md`](./README.md)（运行手册）。**无 `doc/` 目录**，按根 `AGENTS.md` 的约定以本地说明文件为准 |

## 代码地图

| 位置 | 职责 |
|---|---|
| [`src/agentdevelop/basic_graph.py`](./src/agentdevelop/basic_graph.py) | **① 纯图**：`StateGraph`、`TypedDict` 状态、`operator.add` reducer、条件边、`stream`/`invoke`。不调用模型，离线可跑 |
| [`src/agentdevelop/simple_agent.py`](./src/agentdevelop/simple_agent.py) | **② 最小 agent**：`create_agent` + `@tool` 自定义工具，打印消息轨迹让工具循环可见 |
| [`src/agentdevelop/config.py`](./src/agentdevelop/config.py) | 模型工厂：`load_env()` + `build_model() -> ChatOpenAI`，读 `AGENTDEVELOP_*` |
| [`src/agentdevelop/main.py`](./src/agentdevelop/main.py) | argparse 子命令 `graph` / `agent`；默认走离线那段 |
| [`tests/test_basic_graph.py`](./tests/test_basic_graph.py) | 守护第①段纯图，不依赖模型、API Key 与网络 |

## 任务 → 读什么

| 你要做的事 | 先读 |
|---|---|
| 搞懂 LangGraph 图怎么搭 | [`basic_graph.py`](./src/agentdevelop/basic_graph.py)（自顶向下读，注释逐段标注在演示什么） |
| 搞懂 agent 循环 | [`simple_agent.py`](./src/agentdevelop/simple_agent.py)，跑一次看打印的消息轨迹 |
| 换模型 / 加新的兼容端点 | [`config.py`](./src/agentdevelop/config.py) + [`.env.example`](./.env.example) |
| 加一段新样板 | 在 `src/agentdevelop/` 加模块，在 [`main.py`](./src/agentdevelop/main.py) 挂子命令，并在本文件「代码地图」补一行 |
| 让它真正接入链路 | **先别照本目录动手**：先读 [../HealthMind/AGENTS.md](../HealthMind/AGENTS.md)（编排与契约校验）、[../integration-contracts/AGENTS.md](../integration-contracts/AGENTS.md)（事件契约）、[../HealthMindControl/doc/analysis-chain.md](../HealthMindControl/doc/analysis-chain.md)（链路现状） |

## 关键事实与易错点

- **这是学习样板，不是链路组件**：两段示例里的「描述质检」「数词数」都是玩具，与真实的餐食营养分析无关；不要据此认为 AgentDevelop 已经在做分析。
- **`create_react_agent` 已废弃**：`langgraph.prebuilt.create_react_agent` 官方标注废弃，新代码用 `langchain.agents.create_agent`（本目录用的是后者）。
- **`deepagents` 已装但样板未用**：`create_deep_agent` 是后续 agent 框架方向，本次样板刻意只用 LangGraph + `create_agent`，避免一次引入过多概念。
- **环境变量用 `AGENTDEVELOP_*` 前缀**，不是 `OPENAI_*`：避免与机器上其他项目的全局 `OPENAI_API_KEY` 串味。`load_dotenv(override=False)`，已导出的真实环境变量优先。
- **`langchain-openai` 不在初始依赖里**：本目录初始化时只装了 `langchain-anthropic` 与 `langchain-google-genai`；样板选用 OpenAI 兼容端点，才补装 `langchain-openai`。若 `import langchain_openai` 报 `ModuleNotFoundError`，执行 `uv sync`。
- **第①段不需要任何凭据**，第②段才需要 `.env`。因此自动测试只守护第①段；第②段靠人工运行验证。
- **`.env` 不入库**：真实 key 只放在本地 `.env`（见 [`.gitignore`](./.gitignore)），模板 `.env.example` 里的地址是公开端点、不含凭据。
- **`[project.scripts]` 指向 `agentdevelop.main:main`**（不是 `agentdevelop:main`）：让 `__init__.py` 保持干净，避免包初始化与入口互相 import。

## 测试与验证

```bash
uv sync --extra test
uv run agentdevelop graph        # ① 离线纯图：应逐步打印每个节点
uv run agentdevelop graph "嗯"   # 换输入：应走 reject 分支
uv run pytest -q                 # 守护第①段，无需凭据
```

第②段需要真实凭据，不由自动测试执行；配置好 `.env` 后手动运行：

```bash
uv run agentdevelop agent "统计一下这句话的词数：晚饭吃了清蒸鲈鱼"
```

- 测试在 [`tests/`](./tests/)：目前只有 `test_basic_graph.py`（分支走向、边界长度、规整化、reducer 累积）。
- 改动 `basic_graph.py` 的状态结构或分支条件时，同步补/改测试。

## 相关文档

- [README.md](./README.md) — 运行手册（两段样板的跑法、`.env` 变量表）。
- [../AGENTS.md](../AGENTS.md) — 仓库规范、阅读导航与项目背景。
- [../HealthMind/AGENTS.md](../HealthMind/AGENTS.md) — 当前承担 AI 编排的模块（Dify 调用方）。
- [../AgentDeveloper/AGENTS.md](../AgentDeveloper/AGENTS.md) — **另一个目录，勿混淆**：那是已提交的 Dify 提示词技能资产，与本目录（Python/LangGraph）没有代码关系。
- [../HealthMindControl/doc/analysis-chain.md](../HealthMindControl/doc/analysis-chain.md) — AI 分析链路现状与排障。
- 私有：`doc-project/`（项目背景，不提交）；本目录无 `docp/`。
