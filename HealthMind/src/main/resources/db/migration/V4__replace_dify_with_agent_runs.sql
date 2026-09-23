-- One-time cutover. Stop HealthMind consumers and publishers before applying this migration.
-- Only HealthMind runtime rows are cleared; stable task types and tool definitions remain.
TRUNCATE TABLE
    healthmind.ai_tool_invocations,
    healthmind.ai_task_artifacts,
    healthmind.ai_task_results,
    healthmind.integration_outbox,
    healthmind.ai_task_attempts,
    healthmind.ai_tasks,
    healthmind.workflow_release_tools,
    healthmind.workflow_release_audits,
    healthmind.workflow_releases,
    healthmind.integration_inbox;

ALTER TABLE healthmind.workflow_releases DROP CONSTRAINT uk_workflow_releases_dify_version;
ALTER TABLE healthmind.workflow_releases
    DROP COLUMN dify_workspace_id,
    DROP COLUMN dify_app_id,
    DROP COLUMN dify_workflow_id,
    DROP COLUMN dify_workflow_version,
    ADD COLUMN agent_deployment_key VARCHAR(128) NOT NULL,
    ADD COLUMN agent_assistant_id VARCHAR(128) NOT NULL,
    ADD COLUMN agent_artifact_sha256 CHAR(64) NOT NULL
        CHECK (agent_artifact_sha256 ~ '^[0-9a-f]{64}$');
CREATE INDEX idx_workflow_releases_agent_artifact
    ON healthmind.workflow_releases(agent_deployment_key, agent_assistant_id, agent_artifact_sha256);

DROP INDEX healthmind.uk_ai_task_attempts_dify_run;
ALTER TABLE healthmind.ai_task_attempts
    DROP COLUMN dify_workflow_run_id,
    ADD COLUMN agent_run_id UUID,
    ADD COLUMN agent_managed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN agent_next_check_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
CREATE UNIQUE INDEX uk_ai_task_attempts_agent_run
    ON healthmind.ai_task_attempts(agent_run_id) WHERE agent_run_id IS NOT NULL;
CREATE INDEX idx_ai_task_attempts_agent_poll
    ON healthmind.ai_task_attempts(agent_next_check_at) WHERE status = 'running' AND agent_managed;

CREATE FUNCTION healthmind.protect_agent_release_identity() RETURNS TRIGGER AS $$
BEGIN
    IF (OLD.release_version, OLD.agent_deployment_key, OLD.agent_assistant_id,
        OLD.agent_artifact_sha256, OLD.input_schema, OLD.input_schema_sha256,
        OLD.output_schema, OLD.output_schema_sha256, OLD.timeout_seconds, OLD.max_attempts)
        IS DISTINCT FROM
       (NEW.release_version, NEW.agent_deployment_key, NEW.agent_assistant_id,
        NEW.agent_artifact_sha256, NEW.input_schema, NEW.input_schema_sha256,
        NEW.output_schema, NEW.output_schema_sha256, NEW.timeout_seconds, NEW.max_attempts) THEN
        RAISE EXCEPTION 'Agent release identity and contracts are immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_protect_agent_release_identity
    BEFORE UPDATE ON healthmind.workflow_releases
    FOR EACH ROW EXECUTE FUNCTION healthmind.protect_agent_release_identity();

CREATE FUNCTION healthmind.protect_promoted_agent_tools() RETURNS TRIGGER AS $$
DECLARE
    release_status VARCHAR(16);
    pinned_release_id UUID;
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.release_id IS DISTINCT FROM NEW.release_id THEN
        RAISE EXCEPTION 'Tool binding release cannot be changed';
    END IF;
    IF TG_OP = 'DELETE' THEN
        pinned_release_id := OLD.release_id;
    ELSE
        pinned_release_id := NEW.release_id;
    END IF;
    SELECT status INTO release_status
      FROM healthmind.workflow_releases
     WHERE release_id = pinned_release_id
     FOR UPDATE;
    IF release_status <> 'candidate' THEN
        RAISE EXCEPTION 'Tool bindings of a promoted Agent release are immutable';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_protect_promoted_agent_tools
    BEFORE INSERT OR UPDATE OR DELETE ON healthmind.workflow_release_tools
    FOR EACH ROW EXECUTE FUNCTION healthmind.protect_promoted_agent_tools();
