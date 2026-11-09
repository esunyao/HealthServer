# 在 HealthMind 登记餐食分析 Agent

本教程适用于 HealthMind 当前的自托管 Agent 运行链路。登记将一个确定的 Agent 制品与餐食分析任务关联，经过验证后将版本提升为 production。本文的脚本流程使用 PostgreSQL 的 `psql` 客户端及相应数据库权限；以下命令中的示例值都要按实际部署替换。使用 Navicat 执行普通 SQL，请看 [Navicat 手动登记教程](navicat-release.md)。

## 登记在哪里

目标是 **HealthMind 使用的数据库**，不是 Agent 自己的 `nutriathena_agent` schema。登记脚本会在一个事务中写入：

| 表 | 内容 |
|---|---|
| `healthmind.workflow_releases` | Agent 部署身份、输入输出契约、超时及重试配置，初始状态为 `candidate` |
| `healthmind.workflow_release_tools` | 两个 MCP 工具的权限及其 schema 快照，来自活动工具定义 |
| `healthmind.workflow_release_audits` | 登记审计记录 |

来源脚本为 [`register_agent_release.sql`](../../HealthMind/src/main/resources/db/manual/register_agent_release.sql)；提升使用 [`promote_workflow_release.sql`](../../HealthMind/src/main/resources/db/manual/promote_workflow_release.sql)。脚本使用 `psql` 的变量语法 `:'变量名'`，**不要直接作为普通 SQL 粘贴到 Navicat 执行**。

## 1. 登记前检查

在 Navicat 或 `psql` 中连接 HealthMind 实际使用的数据库，执行只读查询：

```sql
SELECT current_database(), inet_server_addr(), inet_server_port();

SELECT tt.task_type_code, tt.active, wr.release_id, wr.release_version, wr.status,
       wr.agent_deployment_key, wr.agent_assistant_id
FROM healthmind.ai_task_types tt
LEFT JOIN healthmind.workflow_releases wr ON wr.task_type_id = tt.task_type_id
WHERE tt.task_type_code = 'nutrition.meal_analysis';

SELECT tool_code, active, auth_scope, request_schema_version, response_schema_version
FROM healthmind.ai_tool_definitions
WHERE tool_code IN ('nutrimemo.capture_context.get', 'orion.nutrition_context.get');
```

核对连接目标与正在运行的 HealthMind 一致；任务类型必须启用，两个工具定义都必须存在且启用。登记脚本会复制当前活动工具的 schema 快照。若已有 production，应先确认切换影响：提升新版本会将旧版本置为 retired；已有任务仍固定在创建时的 release。

Agent 本身还需使用独立数据库，完成其版本化迁移并启动；不要用 HealthMind 的 release 脚本代替 Agent 迁移。确认 Authentik、MCP、模型及图片访问配置可用。`/healthz` 仅检查 Agent 与数据库的连通性，不能证明整条链路可用。

> **日志/依赖变更后的制品摘要**：`artifact_sha256` 由 `NutriAthenaAgent/src/nutriathena_agent/**/*.py`、`migrations/*.sql`、`pyproject.toml`、`uv.lock` 和餐食 skill 资产计算。升级日志库（如新增 `loguru`）或改动源码都会产生新摘要。升级前先 drain/对账旧 release 的 pending/running run；新 worker 只 claim 摘要完全匹配的 run。部署后必须重新登记并提升 release，否则旧 pending run 会一直停留在 pending。

## 2. 准备 release 身份

| `psql` 变量 | 来源和约束 |
|---|---|
| `release_id` | 一个 UUID；必须与 Agent 运行时 `NUTRIATHENA_RELEASE_ID` 完全一致。新版本使用新 UUID，不能使用示例全零 UUID 充当正式身份。 |
| `release_version` | 给这个任务类型的版本名称，例如 `1.0.0`；同任务类型下不能重复。 |
| `deployment_key` | 与 Agent 运行时 `NUTRIATHENA_DEPLOYMENT_KEY` 和 HealthMind 的 `healthmind.agent.deployments` 映射键一致；一个 key 不重新指向另一份制品。 |
| `assistant_id` | 与 Agent 运行时 `NUTRIATHENA_ASSISTANT_ID` 完全一致。 |
| `artifact_sha256` | 根据实际部署的代码、迁移、依赖与 skill 资产计算；见下一节。 |
| `timeout_seconds` | 一次 HealthMind attempt 的超时，范围 1–3600 秒；考虑模型耗时及 Agent 的 `NUTRIATHENA_RUN_TIMEOUT_SECONDS`。 |
| `max_attempts` | 最大 attempt 数，范围 1–10；按实际重试策略决定。 |
| `actor_id`、`reason`、`trace_id` | 登记操作者 UUID、操作原因和追踪标识，用于审计；不填 token 或密码。 |

Agent 的配置可来自环境变量或 `NutriAthenaAgent/.env`，以实际启动进程取得的值为准；现有环境变量优先。注意仓库示例中 Agent key 是 `meal-analysis-v1`，HealthMind 配置中示例映射键是 `meal-v1`，部署时必须自行对齐。HealthMind 的地址映射位于 [`application.yaml`](../../HealthMind/src/main/resources/application.yaml)，也可由部署配置或 Nacos 覆盖；远程地址使用 HTTPS，本机 loopback 开发可以使用 HTTP。

产生新 UUID 可在 PostgreSQL 中执行 `SELECT gen_random_uuid();`。将同一个 UUID 配置给 Agent 并登记为 `release_id`。配置改变后，应使 Agent 以新配置启动；运行中的进程不会因编辑 `.env` 自动切换身份。

## 3. 计算制品摘要

在 **实际运行 Agent 的同一份部署制品**中，从 `NutriAthenaAgent` 目录使用项目 Python 环境执行。Windows Git Bash 可先执行 `source .venv/Scripts/activate` 激活项目虚拟环境：

```bash
python -B -c "from nutriathena_agent.runtime.artifact import compute_artifact_sha256; print(compute_artifact_sha256())"
```

仓库中的制品输入通过 `.gitattributes` 固定 LF 换行，已有 Windows 工作区需将这些文件的工作副本转换为 LF；新检出自动遵守规则。摘要仍按实际字节计算，未跟踪文件、文件内容或依赖锁差异也会影响结果。以目标容器的启动日志或容器内计算结果为最终依据。

输出为 64 位小写十六进制值。实现见 [`artifact.py`](../src/nutriathena_agent/runtime/artifact.py)：它包含 Python 代码、迁移、`NutriAthenaAgent/skills`、`pyproject.toml` 和 `uv.lock`，不是某一个文件的哈希。Agent 启动时也会计算摘要；如果启动后改变了这些文件，重新计算的值可能与运行进程持有的值不一致。先确定制品，再计算并启动与之相同的制品。

## 4. 准备输入、输出 schema 及摘要

| 变量 | 值 |
|---|---|
| `input_schema` | 完整 Kafka capture-ready 事件的 JSON Schema，参考 [`nutrition-capture-ready-v1.schema.json`](../../integration-contracts/src/main/resources/schema/nutrition-capture-ready-v1.schema.json)。 |
| `input_schema_version` | 所选输入契约的版本，例如 `1.0`。 |
| `output_schema` | Agent 成功返回的**裸分析对象**的 JSON Schema，对照 [`MealAnalysis`](../src/nutriathena_agent/meal/contract.py) 的 `overall_confidence` 和 `items` 等字段。 |
| `output_schema_version` | 所选输出契约的版本，由部署者确定。 |
| `input_schema_sha256`、`output_schema_sha256` | 对各自 schema 按 HealthMind 的 [`CanonicalJson`](../../HealthMind/src/main/kotlin/cn/esuny/healthmind/infrastructure/json/CanonicalJson.kt) 递归排序、紧凑序列化后计算的 SHA-256。 |

输入 schema 不是 `/runs` 请求；输出 schema 不是 `nutrition.analysis.completed` 事件信封。HealthMind 对 `needs_review` 有单独处理路径。仓库当前没有独立的 Agent 成功输出 JSON Schema 成品；可以使用当前安装的 Pydantic 从 `MealAnalysis.model_json_schema()` 生成候选，再与 Agent 的模型校验、HealthMind 的 JSON Schema 校验及跨服务事件契约核对。Pydantic 的自定义校验器不一定能表达在生成的 JSON Schema 里，例如空白名称和重复营养素编码；**生成不等于契约验证通过**。

例如在 Agent 环境中查看候选 schema：

```bash
python -B -c "import json; from nutriathena_agent.meal.contract import MealAnalysis; print(json.dumps(MealAnalysis.model_json_schema(), ensure_ascii=False, indent=2))"
```

可以在 Agent 环境、从仓库根目录运行下面的命令，打印可复制到 `psql` 的输入 schema、候选输出 schema 和摘要。它仅接受 ASCII 字符串、整数、布尔值和 null，并将整数值的浮点数转换为整数：在此受限范围内，紧凑 JSON 与 HealthMind 的排序序列化一致。遇到非 ASCII、控制字符、单引号或非整数浮点数会拒绝处理；不要把这个示例哈希方法直接用于任意 JSON。

```bash
cd NutriAthenaAgent
./.venv/Scripts/python.exe -B - <<'PY'
import hashlib
import json
from pathlib import Path
from nutriathena_agent.meal.contract import MealAnalysis

def restricted(value):
    if isinstance(value, dict):
        return {restricted(k): restricted(v) for k, v in value.items()}
    if isinstance(value, list):
        return [restricted(v) for v in value]
    if isinstance(value, str):
        if any(ord(c) < 32 or ord(c) > 126 or c == "'" for c in value):
            raise ValueError('schema contains unsupported characters')
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError('schema contains a non-integer float')
        return int(value)
    if value is None or isinstance(value, (bool, int)):
        return value
    raise TypeError(type(value))

input_path = Path('../integration-contracts/src/main/resources/schema/nutrition-capture-ready-v1.schema.json')
schemas = {
    'input': json.loads(input_path.read_text(encoding='utf-8')),
    'output': MealAnalysis.model_json_schema(),
}
for name, schema in schemas.items():
    text = json.dumps(restricted(schema), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    print(f"\\set {name}_schema '{text}'")
    print(f"\\set {name}_schema_sha256 '{digest}'")
PY
```

保存并审核最终 schema；粘贴输出到下一节的 `psql` 会话时，使用它替换对应的四行占位 `\set`。该命令不会创建文件或连接数据库。使用前仍须用 HealthMind 的 `CanonicalJson.sha256` 核对摘要，并用 `JsonSchemaService` 验证正反例和选定的输出契约；Pydantic 自定义校验仍需单独验证。不要哈希带缩进的原始文件，也不要填 64 位占位符。如果无法完成这些核对，不要提升版本。

## 5. 用 psql 登记 candidate

在 Git Bash 中运行 `psql` 并连接正确的 HealthMind 数据库。使用交互式密码提示或已有安全连接配置，不要把密码写入文档或命令历史。在 `psql` 提示符下设置 `ON_ERROR_STOP`，再设置以下全部变量。带尖括号的内容是需要替换的占位符，JSON 必须是对应完整 schema 的单行内容；不要保留尖括号。

```text
\set ON_ERROR_STOP on
\set release_id '实际-Agent-release-UUID'
\set release_version '1.0.0'
\set deployment_key '实际部署键'
\set assistant_id '实际-assistant-ID'
\set artifact_sha256 '实际制品摘要'
\set input_schema_version '1.0'
\set input_schema '完整单行输入schema的JSON'
\set input_schema_sha256 '已核对的输入schema摘要'
\set output_schema_version '实际输出契约版本'
\set output_schema '完整单行输出schema的JSON'
\set output_schema_sha256 '已核对的输出schema摘要'
\set timeout_seconds '600'
\set max_attempts '1'
\set actor_id '操作者UUID'
\set reason '登记餐食分析Agent'
\set trace_id '本次登记追踪标识'
\i 'E:/ProjectSpace/HealthServer/HealthMind/src/main/resources/db/manual/register_agent_release.sql'
```

`600` 秒和 `1` 次仅演示参数形式，应按实际部署决定；服务器上路径不同则调整 `\i` 路径。大段 JSON 和标识会留在交互命令历史中，因此不得把凭据写进 schema 或变量。若执行报错，检查输出并确认事务已回滚，不要重复插入部分记录。

登记后查询并核对这条 candidate 和两个工具绑定：

```sql
SELECT release_id, release_version, status, agent_deployment_key,
       agent_assistant_id, agent_artifact_sha256
FROM healthmind.workflow_releases
WHERE release_id = :'release_id'::uuid;

SELECT d.tool_code, rt.allowed_scope, rt.required, rt.max_calls,
       rt.request_schema_version, rt.response_schema_version
FROM healthmind.workflow_release_tools rt
JOIN healthmind.ai_tool_definitions d ON d.tool_id = rt.tool_id
WHERE rt.release_id = :'release_id'::uuid;
```

其中 `:'release_id'` 同样是 `psql` 语法；在 Navicat 查询时应替换为实际 UUID 字符串。确保查询恰好返回一条 candidate、两个正确工具，且其身份与运行的 Agent 一致。

## 6. 验证后提升

检查输入/输出 schema 正反例、实际制品摘要、部署 key 地址映射和服务间 OAuth；准备能使用的模型与 MCP，并确认已授权测试数据可用。候选版本不会自动接收常规生产事件；真实端到端验证需要适当的隔离测试环境或已授权 task/attempt，参见 [Agent smoke 说明](../README.md)。无法验证时不要声称已经完成端到端验证。

同一 `psql` 会话中，保留前面的 `release_id`、`actor_id`、`reason` 和 `trace_id`，核对目标确实为 candidate 后执行：

```text
\i 'E:/ProjectSpace/HealthServer/HealthMind/src/main/resources/db/manual/promote_workflow_release.sql'
```

提升脚本会在事务中退役同任务类型的旧 production、提升 candidate 并写审计。提升后再次查询，确认目标为 `production`，且每个任务类型恰好一个 production。HealthMind 没找到 production 时会每 30 秒重试待处理事件；一旦提升成功，这些事件可能随下一次重试开始执行。随后观察任务状态及 Agent 日志，排查 `AGENT_DEPLOYMENT_MISSING`、认证或契约错误。

当前 HealthMindControl 的版本管理页面仍面向旧模型，不能用于登记或提升这个 Agent release。详细的服务边界和身份规则见 [HealthMind Agent 运行契约](../../HealthMind/doc/agent-runtime.md)。
