# 使用 Navicat 登记 Agent release

本教程用普通 PostgreSQL SQL 在 Navicat 中登记和提升餐食分析 Agent，不要求使用 `psql`。仓库的 [`register_agent_release.sql`](../../HealthMind/src/main/resources/db/manual/register_agent_release.sql) 是给人或自动化工具通过 `psql` 使用的；其中 `:'release_id'` 等是 `psql` 客户端变量，Navicat 的普通 SQL 查询不会替你替换。下面的 SQL 完成同样的三类写入，并额外检查任务类型和绑定数量。

## 先理解输入和输出

NutriMemo 通知 HealthMind“有一份餐食要分析”的 Kafka 消息是**输入**，包括事件 ID、用户 ID 和餐食采集 ID。Agent 分析完成后返回的结果是**输出**，包含 `overall_confidence` 和 `items`。Schema 是对这些 JSON 结构的规则说明，不是消息本身。

```text
NutriMemo ──完整 capture-ready 事件──> HealthMind ──任务──> Agent
                   输入 schema                         │
HealthMind <────── {overall_confidence, items} ────────┘
                            输出 schema
```

之后 HealthMind 才把输出包装成 `nutrition.analysis.completed` Kafka 事件；那个事件还有 event_id 等外层字段，不能直接作为 Agent 的输出 schema。`needs_review` 有独立处理路径。输出模型见 [`contracts.py`](../src/nutriathena_agent/meal/contract.py)。

## 1. 准备实际配置

连接 **HealthMind 使用的数据库**。先执行 [release 登记指南](release.md)第 1–3 节的只读检查和制品摘要计算。确认任务类型启用、两个 MCP 工具启用，Agent 已配置、迁移并启动。以下 SQL 顶部必须填写：

| 参数 | 值的来源 |
|---|---|
| `v_release_id` | Agent 实际运行时 `NUTRIATHENA_RELEASE_ID`，UUID 必须完全一致 |
| `v_deployment_key` | Agent 的 `NUTRIATHENA_DEPLOYMENT_KEY`；HealthMind `healthmind.agent.deployments` 中也必须存在同名键和正确地址 |
| `v_assistant_id` | Agent 的 `NUTRIATHENA_ASSISTANT_ID` |
| `v_artifact_sha256` | 在 Agent 实际部署制品上执行指南中的摘要命令，填入 64 位值 |
| `v_actor_id` | 本次登记人的 UUID，用于审计 |
| `v_release_version`、`v_timeout_seconds`、`v_max_attempts` | 自定版本、超时时间及尝试次数；示例不是生产推荐值 |

环境变量可能覆盖 `.env`；以实际运行进程取得的值为准。示例中的 `meal-v1` 和 `meal-analysis-v1` 不是同一个键。不要把密码、token 填入 SQL。

下面内置的输入 schema 来自仓库 capture-ready v1；输出 schema 是按当前 `MealAnalysis` 模型生成的**候选**。摘要由限制在 ASCII/整数 JSON 的教程命令计算，尚需用 HealthMind `CanonicalJson` 核对；输出 schema 需先用 HealthMind `JsonSchemaService`、当前 Agent 和事件契约验证正反例。自定义校验（例如空白名称、重复营养素）不一定能由此 JSON Schema 完整表达。若部署版本或契约有变化，应重新生成、验证并更新 schema 与摘要；release 身份与契约登记后受数据库保护，不能依赖事后原地修正。

## 2. 登记 candidate

在 Navicat 新建查询，替换 `REPLACE_...`、版本、超时等后**整体执行**。`DO` 块是单个事务语句，中途报错不会只提交其中一部分；成功只表示 candidate 已写入，不表示 Agent 已验证或启用。

```sql
DO $register$
DECLARE
    v_release_id UUID := 'REPLACE_RELEASE_UUID';
    v_release_version TEXT := '1.0.0';
    v_deployment_key TEXT := 'REPLACE_DEPLOYMENT_KEY';
    v_assistant_id TEXT := 'REPLACE_ASSISTANT_ID';
    v_artifact_sha256 TEXT := 'REPLACE_ARTIFACT_SHA256';
    v_actor_id UUID := 'REPLACE_ACTOR_UUID';
    v_reason TEXT := '登记 NutriAthenaAgent';
    v_trace_id TEXT := 'register-nutriathena-v1';
    v_timeout_seconds INTEGER := 600;
    v_max_attempts SMALLINT := 1;

    -- 原样保留下面两个 schema；改动时重新计算和核对摘要。
    v_input_schema JSONB := $input$
{"$id":"https://healthmind.local/schema/nutrition-capture-ready-v1.schema.json","$schema":"https://json-schema.org/draft/2020-12/schema","additionalProperties":false,"properties":{"aggregate_id":{"minLength":1,"type":"string"},"aggregate_type":{"const":"meal"},"event_id":{"format":"uuid","type":"string"},"event_type":{"const":"nutrition.capture.ready.v1"},"occurred_at":{"format":"date-time","type":"string"},"payload":{"additionalProperties":false,"properties":{"capture_session_id":{"format":"uuid","type":"string"},"meal_id":{"type":"integer"}},"required":["capture_session_id","meal_id"],"type":"object"},"producer":{"minLength":1,"type":"string"},"schema_version":{"const":"1.0"},"subject_id":{"format":"uuid","type":"string"},"trace_id":{"minLength":1,"type":"string"}},"required":["event_id","event_type","occurred_at","producer","trace_id","subject_id","aggregate_type","aggregate_id","schema_version","payload"],"type":"object"}
    $input$::jsonb;
    v_input_sha256 TEXT := '7b0a9fcc28024d125e107d70eedf1ce6dede858babd1be2eef0a2671d82953dc';

    v_output_schema JSONB := $output$
{"$defs":{"FoodItem":{"additionalProperties":false,"properties":{"confidence":{"maximum":1,"minimum":0,"title":"Confidence","type":"number"},"name":{"maxLength":150,"minLength":1,"title":"Name","type":"string"},"nutrients":{"items":{"$ref":"#/$defs/Nutrient"},"minItems":1,"title":"Nutrients","type":"array"},"weight_grams":{"exclusiveMinimum":0,"title":"Weight Grams","type":"number"}},"required":["name","weight_grams","confidence","nutrients"],"title":"FoodItem","type":"object"},"Nutrient":{"additionalProperties":false,"properties":{"code":{"enum":["ENERGY_KCAL","PROTEIN","FAT","CARBOHYDRATE","SUGAR","DIETARY_FIBER","SODIUM","CALCIUM","IRON","POTASSIUM","VITAMIN_C"],"title":"Code","type":"string"},"value":{"minimum":0,"title":"Value","type":"number"}},"required":["code","value"],"title":"Nutrient","type":"object"}},"additionalProperties":false,"properties":{"items":{"items":{"$ref":"#/$defs/FoodItem"},"maxItems":100,"minItems":1,"title":"Items","type":"array"},"overall_confidence":{"maximum":1,"minimum":0,"title":"Overall Confidence","type":"number"}},"required":["overall_confidence","items"],"title":"MealAnalysis","type":"object"}
    $output$::jsonb;
    v_output_sha256 TEXT := 'ba4710443ba70218043b3c984dd8c383dbec8227f28d33a1d324404b20d9bf26';
    v_task_type_id UUID;
    v_count INTEGER;
BEGIN
    SELECT task_type_id INTO STRICT v_task_type_id
    FROM healthmind.ai_task_types
    WHERE task_type_code = 'nutrition.meal_analysis' AND active;

    INSERT INTO healthmind.workflow_releases (
        release_id, task_type_id, release_version, status,
        agent_deployment_key, agent_assistant_id, agent_artifact_sha256,
        input_schema_version, input_schema, input_schema_sha256,
        output_schema_version, output_schema, output_schema_sha256,
        timeout_seconds, max_attempts, created_by
    ) VALUES (
        v_release_id, v_task_type_id, v_release_version, 'candidate',
        v_deployment_key, v_assistant_id, v_artifact_sha256,
        '1.0', v_input_schema, v_input_sha256,
        '1.0', v_output_schema, v_output_sha256,
        v_timeout_seconds, v_max_attempts, v_actor_id
    );

    INSERT INTO healthmind.workflow_release_tools (
        release_id, tool_id, allowed_scope, required, max_calls, timeout_ms,
        request_schema_version, request_schema, request_schema_sha256,
        response_schema_version, response_schema, response_schema_sha256, created_by
    )
    SELECT v_release_id, tool_id, auth_scope, TRUE, 10, 10000,
           request_schema_version, request_schema, request_schema_sha256,
           response_schema_version, response_schema, response_schema_sha256, v_actor_id
    FROM healthmind.ai_tool_definitions
    WHERE tool_code IN ('nutrimemo.capture_context.get', 'orion.nutrition_context.get')
      AND active;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    IF v_count <> 2 THEN
        RAISE EXCEPTION '需要两个已启用的 MCP 工具，实际绑定 % 个', v_count;
    END IF;

    INSERT INTO healthmind.workflow_release_audits
        (audit_id, release_id, action, from_status, to_status, actor_id, reason, trace_id)
    VALUES
        (gen_random_uuid(), v_release_id, 'created', NULL, 'candidate',
         v_actor_id, v_reason, v_trace_id);
END;
$register$;
```

## 3. 核对 candidate

替换 UUID 后执行两条只读查询：

```sql
SELECT release_id, release_version, status, agent_deployment_key,
       agent_assistant_id, agent_artifact_sha256
FROM healthmind.workflow_releases
WHERE release_id = 'REPLACE_RELEASE_UUID'::uuid;

SELECT d.tool_code, rt.allowed_scope, rt.required, rt.max_calls,
       rt.request_schema_version, rt.response_schema_version
FROM healthmind.workflow_release_tools rt
JOIN healthmind.ai_tool_definitions d ON d.tool_id = rt.tool_id
WHERE rt.release_id = 'REPLACE_RELEASE_UUID'::uuid;
```

必须有一条 `candidate`、两个预期工具，身份与运行的 Agent 一致。确认输入输出正反例、摘要、Agent 与 HealthMind 的地址及 OAuth、MCP 和已授权测试上下文。candidate 不会自动接收正常事件，真实端到端测试需要隔离环境或已授权的 task/attempt；不能仅凭数据库记录声称链路已跑通。

## 4. 提升 production

**执行后，等待中的 Kafka 消息可能在下一次重试时立即开始处理。** 该操作会退役同类型已有 production；先确认新部署已准备好。替换 UUID 后在 Navicat 整体执行：

```sql
DO $promote$
DECLARE
    v_release_id UUID := 'REPLACE_RELEASE_UUID';
    v_actor_id UUID := 'REPLACE_ACTOR_UUID';
    v_reason TEXT := '启用 NutriAthenaAgent';
    v_trace_id TEXT := 'promote-nutriathena-v1';
    v_task_type_id UUID;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('healthmind.workflow.production', 0));

    SELECT task_type_id INTO STRICT v_task_type_id
    FROM healthmind.workflow_releases
    WHERE release_id = v_release_id AND status = 'candidate'
    FOR UPDATE;

    WITH retired AS (
        UPDATE healthmind.workflow_releases
        SET status = 'retired', retired_by = v_actor_id, retired_at = NOW()
        WHERE task_type_id = v_task_type_id AND status = 'production'
        RETURNING release_id
    )
    INSERT INTO healthmind.workflow_release_audits
        (audit_id, release_id, action, from_status, to_status, actor_id, reason, trace_id)
    SELECT gen_random_uuid(), release_id, 'retired', 'production', 'retired',
           v_actor_id, v_reason, v_trace_id
    FROM retired;

    UPDATE healthmind.workflow_releases
    SET status = 'production', promoted_by = v_actor_id, promoted_at = NOW()
    WHERE release_id = v_release_id AND status = 'candidate';

    INSERT INTO healthmind.workflow_release_audits
        (audit_id, release_id, action, from_status, to_status, actor_id, reason, trace_id)
    VALUES
        (gen_random_uuid(), v_release_id, 'promoted', 'candidate', 'production',
         v_actor_id, v_reason, v_trace_id);
END;
$promote$;
```

再次查询确认目标状态为 `production`，再观察 HealthMind 和 Agent 日志。登记和提升都不会自动修好 Agent 地址、token、模型或 MCP 配置。
