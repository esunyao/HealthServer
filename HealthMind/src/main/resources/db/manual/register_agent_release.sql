-- Run with psql -v ON_ERROR_STOP=1 and the variables listed in doc/README.md.
-- A deployment key is immutable: never repoint an active key to another build.
BEGIN;

INSERT INTO healthmind.workflow_releases (
    release_id, task_type_id, release_version, status,
    agent_deployment_key, agent_assistant_id, agent_artifact_sha256,
    input_schema_version, input_schema, input_schema_sha256,
    output_schema_version, output_schema, output_schema_sha256,
    timeout_seconds, max_attempts, created_by
)
SELECT
    :'release_id'::uuid, task_type_id, :'release_version', 'candidate',
    :'deployment_key', :'assistant_id', :'artifact_sha256',
    :'input_schema_version', :'input_schema'::jsonb, :'input_schema_sha256',
    :'output_schema_version', :'output_schema'::jsonb, :'output_schema_sha256',
    :'timeout_seconds'::integer, :'max_attempts'::smallint, :'actor_id'::uuid
FROM healthmind.ai_task_types
WHERE task_type_code = 'nutrition.meal_analysis' AND active;

INSERT INTO healthmind.workflow_release_tools
    (release_id, tool_id, allowed_scope, required, max_calls, timeout_ms, created_by)
SELECT :'release_id'::uuid, tool_id, auth_scope, TRUE, 10, 10000, :'actor_id'::uuid
FROM healthmind.ai_tool_definitions
WHERE tool_code IN ('nutrimemo.capture_context.get', 'orion.nutrition_context.get') AND active;

DO $$
BEGIN
    IF (SELECT COUNT(*) FROM healthmind.ai_tool_definitions
        WHERE tool_code IN ('nutrimemo.capture_context.get', 'orion.nutrition_context.get') AND active) <> 2 THEN
        RAISE EXCEPTION 'Both HealthMind MCP tool definitions must be active';
    END IF;
END;
$$;

INSERT INTO healthmind.workflow_release_audits
    (audit_id, release_id, action, from_status, to_status, actor_id, reason, trace_id)
VALUES (gen_random_uuid(), :'release_id'::uuid, 'created', NULL, 'candidate', :'actor_id'::uuid, :'reason', :'trace_id');

COMMIT;
