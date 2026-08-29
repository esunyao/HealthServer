CREATE SCHEMA IF NOT EXISTS healthmind;
SET search_path TO healthmind, public;

CREATE TABLE ai_task_types (
    task_type_id UUID PRIMARY KEY,
    task_type_code VARCHAR(64) NOT NULL UNIQUE CHECK (task_type_code ~ '^[a-z][a-z0-9_.-]*$'),
    domain_code VARCHAR(32) NOT NULL CHECK (domain_code ~ '^[a-z][a-z0-9_]*$'),
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    default_invocation_mode VARCHAR(16) NOT NULL DEFAULT 'async' CHECK (default_invocation_mode IN ('async','sync')),
    default_timeout_seconds INTEGER NOT NULL DEFAULT 120 CHECK (default_timeout_seconds BETWEEN 1 AND 3600),
    max_attempts SMALLINT NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 10),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ai_task_types_domain_active ON ai_task_types(domain_code, active);

CREATE TABLE workflow_releases (
    release_id UUID PRIMARY KEY,
    task_type_id UUID NOT NULL REFERENCES ai_task_types(task_type_id),
    release_version VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate','production','retired')),
    dify_workspace_id VARCHAR(128) NOT NULL,
    dify_app_id VARCHAR(128) NOT NULL,
    dify_workflow_id VARCHAR(128) NOT NULL,
    dify_workflow_version VARCHAR(128) NOT NULL,
    input_schema_version VARCHAR(32) NOT NULL,
    input_schema JSONB NOT NULL CHECK (jsonb_typeof(input_schema) = 'object'),
    input_schema_sha256 CHAR(64) NOT NULL CHECK (input_schema_sha256 ~ '^[0-9a-f]{64}$'),
    output_schema_version VARCHAR(32) NOT NULL,
    output_schema JSONB NOT NULL CHECK (jsonb_typeof(output_schema) = 'object'),
    output_schema_sha256 CHAR(64) NOT NULL CHECK (output_schema_sha256 ~ '^[0-9a-f]{64}$'),
    timeout_seconds INTEGER NOT NULL CHECK (timeout_seconds BETWEEN 1 AND 3600),
    max_attempts SMALLINT NOT NULL CHECK (max_attempts BETWEEN 1 AND 10),
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    promoted_by UUID,
    promoted_at TIMESTAMPTZ,
    retired_by UUID,
    retired_at TIMESTAMPTZ,
    CONSTRAINT uk_workflow_releases_task_version UNIQUE (task_type_id, release_version),
    CONSTRAINT uk_workflow_releases_dify_version UNIQUE (dify_workspace_id, dify_app_id, dify_workflow_id, dify_workflow_version),
    CONSTRAINT ck_workflow_releases_lifecycle CHECK (
        (status <> 'production' OR promoted_at IS NOT NULL) AND
        (status <> 'retired' OR retired_at IS NOT NULL)
    )
);
CREATE UNIQUE INDEX uk_workflow_releases_production ON workflow_releases(task_type_id) WHERE status = 'production';

CREATE TABLE workflow_release_audits (
    audit_id UUID PRIMARY KEY,
    release_id UUID NOT NULL REFERENCES workflow_releases(release_id),
    action VARCHAR(16) NOT NULL CHECK (action IN ('created','promoted','rolled_back','retired')),
    from_status VARCHAR(16) CHECK (from_status IS NULL OR from_status IN ('candidate','production','retired')),
    to_status VARCHAR(16) NOT NULL CHECK (to_status IN ('candidate','production','retired')),
    actor_id UUID,
    reason TEXT NOT NULL,
    change_metadata JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(change_metadata) = 'object'),
    trace_id VARCHAR(64),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_workflow_release_audits_release_time ON workflow_release_audits(release_id, occurred_at DESC);

CREATE TABLE ai_tool_definitions (
    tool_id UUID PRIMARY KEY,
    tool_code VARCHAR(64) NOT NULL UNIQUE CHECK (tool_code ~ '^[a-z][a-z0-9_.-]*$'),
    display_name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    owner_service VARCHAR(64) NOT NULL,
    nacos_service_name VARCHAR(128) NOT NULL,
    operation_id VARCHAR(128) NOT NULL,
    auth_scope VARCHAR(128) NOT NULL,
    request_schema_version VARCHAR(32) NOT NULL,
    request_schema JSONB NOT NULL CHECK (jsonb_typeof(request_schema) = 'object'),
    request_schema_sha256 CHAR(64) NOT NULL CHECK (request_schema_sha256 ~ '^[0-9a-f]{64}$'),
    response_schema_version VARCHAR(32) NOT NULL,
    response_schema JSONB NOT NULL CHECK (jsonb_typeof(response_schema) = 'object'),
    response_schema_sha256 CHAR(64) NOT NULL CHECK (response_schema_sha256 ~ '^[0-9a-f]{64}$'),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ai_tool_definitions_owner_active ON ai_tool_definitions(owner_service, active);

CREATE TABLE workflow_release_tools (
    release_id UUID NOT NULL REFERENCES workflow_releases(release_id) ON DELETE CASCADE,
    tool_id UUID NOT NULL REFERENCES ai_tool_definitions(tool_id),
    allowed_scope VARCHAR(128) NOT NULL,
    required BOOLEAN NOT NULL DEFAULT FALSE,
    max_calls SMALLINT NOT NULL DEFAULT 1 CHECK (max_calls BETWEEN 1 AND 100),
    timeout_ms INTEGER NOT NULL DEFAULT 5000 CHECK (timeout_ms BETWEEN 100 AND 60000),
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (release_id, tool_id)
);
CREATE INDEX idx_workflow_release_tools_tool ON workflow_release_tools(tool_id);

CREATE TABLE ai_tasks (
    task_id UUID PRIMARY KEY,
    task_type_id UUID NOT NULL REFERENCES ai_task_types(task_type_id),
    workflow_release_id UUID NOT NULL REFERENCES workflow_releases(release_id),
    request_event_id UUID,
    requester_service VARCHAR(64) NOT NULL,
    subject_id UUID,
    aggregate_type VARCHAR(64) NOT NULL,
    aggregate_id VARCHAR(128) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    invocation_mode VARCHAR(16) NOT NULL DEFAULT 'async' CHECK (invocation_mode IN ('async','sync')),
    status VARCHAR(16) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed','cancelled','expired')),
    priority SMALLINT NOT NULL DEFAULT 5 CHECK (priority BETWEEN 0 AND 9),
    trace_id VARCHAR(64) NOT NULL,
    input_schema_version VARCHAR(32) NOT NULL,
    input_digest CHAR(64) NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
    context_manifest JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(context_manifest) = 'object'),
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deadline_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failure_code VARCHAR(64),
    failure_message VARCHAR(1000),
    retention_until TIMESTAMPTZ NOT NULL,
    lock_version BIGINT NOT NULL DEFAULT 0 CHECK (lock_version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uk_ai_tasks_idempotency UNIQUE (requester_service, task_type_id, idempotency_key),
    CONSTRAINT ck_ai_tasks_lifecycle CHECK (
        (status <> 'running' OR started_at IS NOT NULL) AND
        (status NOT IN ('succeeded','failed','cancelled','expired') OR completed_at IS NOT NULL) AND
        (status <> 'failed' OR failure_code IS NOT NULL)
    )
);
CREATE UNIQUE INDEX uk_ai_tasks_request_event ON ai_tasks(request_event_id) WHERE request_event_id IS NOT NULL;
CREATE INDEX idx_ai_tasks_dispatch ON ai_tasks(status, next_attempt_at, priority, scheduled_at) WHERE status IN ('queued','running');
CREATE INDEX idx_ai_tasks_subject_created ON ai_tasks(subject_id, created_at DESC);
CREATE INDEX idx_ai_tasks_aggregate ON ai_tasks(aggregate_type, aggregate_id);
CREATE INDEX idx_ai_tasks_release ON ai_tasks(workflow_release_id);
CREATE INDEX idx_ai_tasks_trace ON ai_tasks(trace_id);
CREATE INDEX idx_ai_tasks_deadline ON ai_tasks(deadline_at) WHERE status IN ('queued','running') AND deadline_at IS NOT NULL;
CREATE INDEX idx_ai_tasks_retention ON ai_tasks(retention_until);

CREATE TABLE ai_task_attempts (
    attempt_id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES ai_tasks(task_id) ON DELETE CASCADE,
    attempt_no SMALLINT NOT NULL CHECK (attempt_no BETWEEN 1 AND 10),
    status VARCHAR(16) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','succeeded','failed','timed_out','cancelled')),
    dify_workflow_run_id VARCHAR(128),
    provider_name VARCHAR(64),
    model_name VARCHAR(128),
    model_version VARCHAR(128),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    duration_ms BIGINT CHECK (duration_ms IS NULL OR duration_ms >= 0),
    timeout_ms INTEGER NOT NULL CHECK (timeout_ms BETWEEN 1000 AND 3600000),
    input_tokens BIGINT CHECK (input_tokens IS NULL OR input_tokens >= 0),
    output_tokens BIGINT CHECK (output_tokens IS NULL OR output_tokens >= 0),
    estimated_cost NUMERIC(18,6) CHECK (estimated_cost IS NULL OR estimated_cost >= 0),
    cost_currency CHAR(3) CHECK (cost_currency IS NULL OR cost_currency ~ '^[A-Z]{3}$'),
    failure_category VARCHAR(32) CHECK (failure_category IS NULL OR failure_category IN ('transient','permanent','contract','timeout','cancelled')),
    failure_code VARCHAR(64),
    failure_message VARCHAR(1000),
    execution_metadata JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(execution_metadata) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uk_ai_task_attempts_task_no UNIQUE (task_id, attempt_no),
    CONSTRAINT ck_ai_task_attempts_lifecycle CHECK (
        (status <> 'running' OR started_at IS NOT NULL) AND
        (status NOT IN ('succeeded','failed','timed_out','cancelled') OR finished_at IS NOT NULL) AND
        (status NOT IN ('failed','timed_out','cancelled') OR failure_category IS NOT NULL)
    )
);
CREATE UNIQUE INDEX uk_ai_task_attempts_dify_run ON ai_task_attempts(dify_workflow_run_id) WHERE dify_workflow_run_id IS NOT NULL;
CREATE INDEX idx_ai_task_attempts_status_created ON ai_task_attempts(status, created_at);

CREATE TABLE ai_task_results (
    result_id UUID PRIMARY KEY,
    task_id UUID NOT NULL UNIQUE REFERENCES ai_tasks(task_id) ON DELETE CASCADE,
    output_schema_version VARCHAR(32) NOT NULL,
    result_payload JSONB NOT NULL CHECK (jsonb_typeof(result_payload) = 'object'),
    result_sha256 CHAR(64) NOT NULL CHECK (result_sha256 ~ '^[0-9a-f]{64}$'),
    confidence NUMERIC(5,4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    produced_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ai_task_results_expiry ON ai_task_results(expires_at);

CREATE TABLE ai_task_artifacts (
    artifact_id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES ai_tasks(task_id) ON DELETE CASCADE,
    attempt_id UUID REFERENCES ai_task_attempts(attempt_id) ON DELETE CASCADE,
    artifact_type VARCHAR(32) NOT NULL CHECK (artifact_type IN ('input_image','input_document','raw_request','raw_response','trace_export','other')),
    storage_provider VARCHAR(16) NOT NULL DEFAULT 'rustfs' CHECK (storage_provider = 'rustfs'),
    bucket_name VARCHAR(63) NOT NULL,
    object_key VARCHAR(1024) NOT NULL,
    media_type VARCHAR(128) NOT NULL,
    byte_size BIGINT NOT NULL CHECK (byte_size >= 0),
    content_sha256 CHAR(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    encryption_key_ref VARCHAR(256),
    status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active','deleted','purge_failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT uk_ai_task_artifacts_object UNIQUE (bucket_name, object_key),
    CONSTRAINT ck_ai_task_artifacts_lifecycle CHECK (
        (status <> 'deleted' OR deleted_at IS NOT NULL) AND
        (status <> 'active' OR deleted_at IS NULL)
    )
);
CREATE INDEX idx_ai_task_artifacts_task ON ai_task_artifacts(task_id);
CREATE INDEX idx_ai_task_artifacts_attempt ON ai_task_artifacts(attempt_id) WHERE attempt_id IS NOT NULL;
CREATE INDEX idx_ai_task_artifacts_expiry ON ai_task_artifacts(status, expires_at);

CREATE TABLE ai_tool_invocations (
    invocation_id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES ai_tasks(task_id) ON DELETE CASCADE,
    attempt_id UUID NOT NULL REFERENCES ai_task_attempts(attempt_id) ON DELETE CASCADE,
    release_id UUID NOT NULL REFERENCES workflow_releases(release_id),
    tool_id UUID NOT NULL REFERENCES ai_tool_definitions(tool_id),
    tool_call_id VARCHAR(128) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    caller_subject_id UUID,
    authorized_scope VARCHAR(128),
    status VARCHAR(16) NOT NULL DEFAULT 'requested' CHECK (status IN ('requested','authorized','running','succeeded','failed','denied','timed_out')),
    request_schema_version VARCHAR(32) NOT NULL,
    request_sha256 CHAR(64) NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    response_schema_version VARCHAR(32),
    response_sha256 CHAR(64) CHECK (response_sha256 IS NULL OR response_sha256 ~ '^[0-9a-f]{64}$'),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms BIGINT CHECK (duration_ms IS NULL OR duration_ms >= 0),
    failure_code VARCHAR(64),
    failure_message VARCHAR(1000),
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uk_ai_tool_invocations_call UNIQUE (attempt_id, tool_call_id),
    CONSTRAINT uk_ai_tool_invocations_idempotency UNIQUE (tool_id, idempotency_key),
    CONSTRAINT ck_ai_tool_invocations_lifecycle CHECK (
        (status NOT IN ('succeeded','failed','denied','timed_out') OR completed_at IS NOT NULL) AND
        (status NOT IN ('failed','denied','timed_out') OR failure_code IS NOT NULL) AND
        (status NOT IN ('authorized','running','succeeded') OR authorized_scope IS NOT NULL)
    )
);
CREATE INDEX idx_ai_tool_invocations_task_time ON ai_tool_invocations(task_id, created_at);
CREATE INDEX idx_ai_tool_invocations_tool_status ON ai_tool_invocations(tool_id, status, created_at);

CREATE TABLE integration_inbox (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(128) NOT NULL,
    schema_version VARCHAR(32) NOT NULL,
    producer VARCHAR(64) NOT NULL,
    subject_id UUID,
    aggregate_type VARCHAR(64) NOT NULL,
    aggregate_id VARCHAR(128) NOT NULL,
    trace_id VARCHAR(64) NOT NULL,
    payload_sha256 CHAR(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    status VARCHAR(16) NOT NULL DEFAULT 'processing' CHECK (status IN ('processing','processed','failed')),
    attempt_count INTEGER NOT NULL DEFAULT 1 CHECK (attempt_count >= 1),
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    failure_code VARCHAR(64),
    failure_message VARCHAR(1000),
    retention_until TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_integration_inbox_status_received ON integration_inbox(status, received_at);
CREATE INDEX idx_integration_inbox_type_received ON integration_inbox(event_type, received_at);
CREATE INDEX idx_integration_inbox_aggregate ON integration_inbox(aggregate_type, aggregate_id);
CREATE INDEX idx_integration_inbox_retention ON integration_inbox(retention_until);

CREATE TABLE integration_outbox (
    event_id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES ai_tasks(task_id) ON DELETE CASCADE,
    event_type VARCHAR(128) NOT NULL,
    schema_version VARCHAR(32) NOT NULL,
    producer VARCHAR(64) NOT NULL DEFAULT 'HealthMind',
    aggregate_type VARCHAR(64) NOT NULL,
    aggregate_id VARCHAR(128) NOT NULL,
    destination_key VARCHAR(64) NOT NULL,
    partition_key VARCHAR(128) NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    payload_sha256 CHAR(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    status VARCHAR(16) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','publishing','published','failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    failure_code VARCHAR(64),
    failure_message VARCHAR(1000),
    trace_id VARCHAR(64) NOT NULL,
    retention_until TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_integration_outbox_lifecycle CHECK (
        (status <> 'published' OR published_at IS NOT NULL) AND
        (status <> 'failed' OR failure_code IS NOT NULL)
    )
);
CREATE INDEX idx_integration_outbox_delivery ON integration_outbox(status, next_attempt_at, created_at) WHERE status IN ('pending','failed');
CREATE INDEX idx_integration_outbox_task ON integration_outbox(task_id);
CREATE INDEX idx_integration_outbox_retention ON integration_outbox(retention_until);

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ai_task_types_updated_at BEFORE UPDATE ON ai_task_types
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_ai_tool_definitions_updated_at BEFORE UPDATE ON ai_tool_definitions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_ai_tasks_updated_at BEFORE UPDATE ON ai_tasks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
