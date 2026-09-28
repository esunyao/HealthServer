# HealthServer

本仓库包含 Gateway、Orion、NutriMemo、HealthMind、NutriAthenaAgent 和跨服务集成契约。AI 膳食分析由 HealthMind 的任务编排/MCP 授权与 NutriAthenaAgent 的持久化 Agent run 协作；运行时不再调用 Dify，AgentDeveloper 中原 Dify 技能资产继续作为膳食分析技能来源。`HealthMindControl` 的模型版本管理页面仍面向旧模型，尚不支持本轮接入的 Agent release（新运行端）；本轮不修改 HMC。跨服务 AI 链路的本地管理与手动调试入口见 [HealthMindControl](HealthMindControl/README.md)，运行端说明见 [NutriAthenaAgent](NutriAthenaAgent/README.md)。

阅读入口：根 [AGENTS.md](AGENTS.md)（规范、项目背景与阅读导航）→ 各模块 `AGENTS.md`（模块导航，如 [Orion](Orion/AGENTS.md)）→ 模块 `doc/README.md`（公开概览）。
