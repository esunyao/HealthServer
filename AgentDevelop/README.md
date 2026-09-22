# AgentDevelop

用 LangGraph 写 AI 编排的**学习样板**。目前只用于学 LangGraph 怎么组织，**还没有**接入 HealthServer
的 AI 分析链路，也没有替代 Dify 当前的运行时位置。

AI 导航入口见 [`AGENTS.md`](./AGENTS.md)（读什么、去哪找、边界在哪）。

## 两段样板

| 段落 | 文件 | 需要模型吗 | 演示什么 |
|---|---|---|---|
| ① 纯图 | [`src/agentdevelop/basic_graph.py`](./src/agentdevelop/basic_graph.py) | 否，离线可跑 | `StateGraph`、状态与 reducer、节点、条件边、`stream` 与 `invoke` |
| ② 最小 agent | [`src/agentdevelop/simple_agent.py`](./src/agentdevelop/simple_agent.py) | 是 | `create_agent` + 自定义工具，看 agent 的工具循环 |

## 跑起来

```bash
cd AgentDevelop

# 安装（含测试依赖）
uv sync --extra test

# ① 纯图，不需要任何凭据
uv run agentdevelop graph
uv run agentdevelop graph "嗯"        # 换输入：太短会走 reject 分支

# 测试
uv run pytest -q
```

## 配模型（只有第②段需要）

复制模板并填写：

```bash
cp .env.example .env
```

| 变量 | 必填 | 说明 |
|---|---|---|
| `AGENTDEVELOP_API_KEY` | 是 | 兼容端点的 API Key |
| `AGENTDEVELOP_BASE_URL` | 是 | 兼容端点地址，如 `https://api.deepseek.com/v1` |
| `AGENTDEVELOP_MODEL` | 否 | 默认 `deepseek-chat` |

然后：

```bash
uv run agentdevelop agent
uv run agentdevelop agent "统计一下这句话的词数：晚饭吃了清蒸鲈鱼"
```

`.env` 不在版本控制内；已在 shell 中导出的同名环境变量优先于 `.env`。

## 依赖

Python 3.11（`uv` 管理）。除 `langgraph` / `langchain` 外，`deepagents` 也已安装但**样板暂未使用**，
属于后续方向，见 [`AGENTS.md`](./AGENTS.md) 的「关键事实与易错点」。
