# 待办：梳理 HealthMind 契约版本与跨服务兼容策略

- 状态：待调查、待设计、待实施；本文不是已批准的实施方案。
- 范围：HealthMind、NutriMemo、NutriAthenaAgent、integration-contracts 的相关契约；必要时检查其他调用方。
- 背景：用户在登记餐食分析 Agent release 时发现，MCP 工具 schema 的内容及版本分散在数据库迁移 SQL 和数据库记录中，同时 HealthMind 使用版本字符串判断 NutriMemo 是否返回餐食备注。用户认为当前版本控制混乱，希望后续统一梳理。
- 本文只记录待办；尚未修改生产代码、数据库、现有迁移或运行中的 release，也未对新设计做决定。

## 已核实的现状

1. [V2 迁移](../../HealthMind/src/main/resources/db/migration/V2__seed_stable_definitions.sql)在 SQL 中内嵌 MCP 工具的请求、响应 JSON Schema、版本号和摘要，并写入 `healthmind.ai_tool_definitions`。这些 MCP 工具 schema 并不都在 `integration-contracts/src/main/resources/schema/` 中以独立文件存在。
2. [V7 迁移](../../HealthMind/src/main/resources/db/migration/V7__add_meal_notes_to_capture_context.sql)将 `nutrimemo.capture_context.get` 的当前响应 schema 更新为 `1.1`，加入可空 `notes`；原 `1.0` 定义见 V2。版本字符串存于 `response_schema_version`，schema JSON 与摘要存于相邻字段，不是从 JSON 文件名自动推导。
3. [登记脚本](../../HealthMind/src/main/resources/db/manual/register_agent_release.sql)会将当前活动工具的版本、schema、摘要和授权等复制到 `healthmind.workflow_release_tools`；[工具授权与调用](../../HealthMind/src/main/kotlin/cn/esuny/healthmind/infrastructure/database/ToolInvocationRepository.kt)使用任务固定 release 的快照。[HealthMindMcpTools](../../HealthMind/src/main/kotlin/cn/esuny/healthmind/interfaces/mcp/HealthMindMcpTools.kt)根据固定的请求/响应 schema 执行校验。V7 有意不修改旧 release 和绑定。
4. [InternalContextClient](../../HealthMind/src/main/kotlin/cn/esuny/healthmind/infrastructure/http/InternalContextClient.kt)构造 NutriMemo 请求时使用 `grant.responseSchemaVersion != "1.0"` 作为 `include_meal_notes`；[NutriMemo 接口](../../NutriMemo/src/main/kotlin/cn/esuny/nutrimemo/internal/CaptureAnalysisContext.kt)按该标志决定是否返回非空备注。现有 [测试](../../HealthMind/src/test/kotlin/cn/esuny/healthmind/infrastructure/http/InternalContextClientTest.kt)涉及固定版本的备注能力。
5. `workflow_releases` 的 input/output schema 及其版本属于整个任务的输入和 Agent 成功输出契约；MCP 工具的 request/response schema 是另一套；`integration-contracts` 中 Kafka 事件 schema 与 Agent HTTP protocol schema 又各自描述不同边界。不可把同名 `1.0` / `1.1` 当作同一版本，也不可用完成事件的信封 schema 直接替代 Agent 裸输出 schema。
6. 当前 Agent 成功结果模型见 [contracts.py](../../NutriAthenaAgent/src/nutriathena_agent/contracts.py)，release 登记教程中的 schema 是从模型生成的候选，不应仅凭版本标签或生成成功就视作完整契约验证。`needs_review` 由 [HealthMind 任务执行逻辑](../../HealthMind/src/main/kotlin/cn/esuny/healthmind/application/service/TaskExecutionService.kt)单独处理。

## 为什么需要治理

- **隐含行为与版本标签耦合**：当前 `!= "1.0"` 将任意不是 `1.0` 的值都视为支持备注，包括未来版本或误填值；这不是有界的版本兼容判断。若版本标签与 schema 内容不一致，可能请求与固定 schema 不相容的字段，造成响应契约校验失败或意料之外的行为。实际影响仍须按部署和具体数据验证。
- **定义与溯源分散**：工具 schema 在迁移 SQL、数据库当前定义、release 快照中出现；Kafka schema 和 Agent 模型又在其他位置。查找定义、比较历史版本、确认版本号与摘要对应都不直观。应保留数据库快照的运行时隔离价值，同时明确受版本控制的权威来源和生成/校验流程。
- **版本名称并非自动语义**：`1.1` 本身不会证明支持某字段，也不自动保证 schema、摘要和实现一致；输入/输出、工具、Kafka、Agent HTTP 等契约的版本含义需要分别定义。
- **历史兼容有真实约束**：旧 release 可能固定了 `1.0`，其响应 schema 不允许新增未声明字段。不能直接删除兼容逻辑、无条件返回备注，或修改既有 release 快照来简化实现。

## 后续调查与设计任务

- [ ] 盘点各条契约边界的权威定义、版本标记、调用方、数据库当前定义、release 快照及摘要来源；明确哪些是代码仓库契约、哪些是部署时生成或登记的快照。调查实际已有版本/调用方前，不假定所有环境都只有 `1.0` 和 `1.1`。
- [ ] 设计可追溯的 MCP 工具 schema 管理方式：版本与 schema 显式对应、按固定规则计算并校验摘要、检测同版本不同内容和未知版本；评估独立版本化文件与其他方案，说明如何避免和已应用迁移内嵌内容产生多个权威来源。
- [ ] 重新设计 `include_meal_notes` 的兼容判定。比较显式能力/契约元数据、明确的受支持版本映射等方案；定义未知版本的明确失败行为与可观测错误。不能仅把字符串比较换成看似通用的版本大小比较就假定未来版本兼容。
- [ ] 明确输入事件、Agent 输出、MCP 工具及 Agent HTTP 协议各自的版本策略、来源、兼容范围、登记方式；明确版本号、schema 内容及 canonical SHA-256 的关系，防止标签与内容漂移。
- [ ] 检查 Agent 的 Pydantic 模型生成的 JSON Schema 能否表达所有业务校验；重点核对非空白、重复营养素等自定义校验，以及 HealthMind 的 Draft 2020-12 校验和下游 Kafka 事件契约。明确 `needs_review` 路径，不把不同边界的 schema 混用。
- [ ] 梳理 release 生命周期、登记和晋升时的工具 schema 快照、能力元数据与制品身份；设计向后兼容的迁移和回滚方式，以及运行中、重试中任务如何保持原 release。
- [ ] 检查并更新受影响模块的公开 `doc/`、必要的模块 `AGENTS.md` 导航与登记教程。现有 [psql 教程](../../NutriAthenaAgent/doc/release.md)和 [Navicat 教程](../../NutriAthenaAgent/doc/navicat-release.md)的候选 schema/摘要必须结合最终契约重新核验，不能仅因已写入文档就默认受支持。

## 验收条件

- [ ] 已记录明确的版本/能力兼容矩阵，至少覆盖已有 `1.0`、`1.1`、未知/不受支持版本及标签与 schema 不一致的处理，并明确错误与日志不得泄露用户敏感数据。
- [ ] 自动化测试覆盖：旧 release 不请求且不返回超出旧 schema 的备注；支持备注的 release 在有备注和无备注时正确处理；未知版本按设计明确失败；新旧 release 的快照相互独立。
- [ ] schema 版本、JSON 和摘要的对应关系有可复现检查；验证请求/响应及 Agent 输出的有效和无效例子，同时验证跨服务事件契约与 `needs_review` 路径。
- [ ] 迁移方案对已存在 release、任务和数据库有说明与验证，已应用的 Flyway 迁移不改写；不破坏受固定 release 保护的历史数据。
- [ ] 完成相关模块测试及仓库要求的检查，并明确记录哪些真实 OAuth、MCP、数据库、模型和端到端环境验证尚未完成。

## 工作边界

这是独立治理事项，不应借登记 release 之机直接改数据库生产记录、静默改历史 schema 快照或变更工具授权。若要实施，先根据当前源码与实际部署状态复核本文，确定方案和迁移范围；本文不要求某一种具体架构。
