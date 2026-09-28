CREATE TABLE nutriathena_agent.agent_threads (
    thread_id UUID PRIMARY KEY,
    task_id UUID NOT NULL,
    attempt_id UUID NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_agent_threads_fixed_id CHECK (thread_id = attempt_id),
    CONSTRAINT uq_agent_threads_scope UNIQUE (thread_id, task_id, attempt_id)
);

CREATE TABLE nutriathena_agent.agent_runs (
    run_id UUID PRIMARY KEY,
    thread_id UUID NOT NULL,
    task_id UUID NOT NULL,
    attempt_id UUID NOT NULL UNIQUE,
    release_id UUID NOT NULL,
    request_payload JSONB NOT NULL CHECK (jsonb_typeof(request_payload) = 'object'),
    request_sha256 CHAR(64) NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    requested_assistant_id VARCHAR(128) NOT NULL CHECK (length(requested_assistant_id) > 0),
    requested_artifact_sha256 CHAR(64) NOT NULL CHECK (requested_artifact_sha256 ~ '^[0-9a-f]{64}$'),
    agent_deployment_key VARCHAR(128) NOT NULL,
    agent_assistant_id VARCHAR(128) NOT NULL,
    agent_artifact_sha256 CHAR(64) NOT NULL CHECK (agent_artifact_sha256 ~ '^[0-9a-f]{64}$'),
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    result_payload JSONB NULL CHECK (result_payload IS NULL OR jsonb_typeof(result_payload) = 'object'),
    result_sha256 CHAR(64) NULL CHECK (result_sha256 IS NULL OR result_sha256 ~ '^[0-9a-f]{64}$'),
    error_code VARCHAR(64) NULL,
    error_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    cancel_requested_at TIMESTAMPTZ NULL,
    lease_owner VARCHAR(128) NULL,
    lease_expires_at TIMESTAMPTZ NULL,
    lease_version BIGINT NOT NULL DEFAULT 0 CHECK (lease_version >= 0),
    result_expires_at TIMESTAMPTZ NULL,
    result_purged_at TIMESTAMPTZ NULL,
    retention_until TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_agent_runs_thread_scope
        FOREIGN KEY (thread_id, task_id, attempt_id)
        REFERENCES nutriathena_agent.agent_threads (thread_id, task_id, attempt_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_agent_runs_status CHECK (status IN ('pending', 'running', 'success', 'error', 'interrupted')),
    CONSTRAINT ck_agent_runs_lease_pair CHECK ((lease_owner IS NULL) = (lease_expires_at IS NULL)),
    CONSTRAINT ck_agent_runs_status_fields CHECK (
        (status = 'pending'
            AND started_at IS NULL AND completed_at IS NULL AND retention_until IS NULL
            AND lease_owner IS NULL AND lease_expires_at IS NULL
            AND result_payload IS NULL AND result_sha256 IS NULL
            AND error_code IS NULL AND error_message IS NULL
            AND result_expires_at IS NULL AND result_purged_at IS NULL)
        OR
        (status = 'running'
            AND started_at IS NOT NULL AND completed_at IS NULL AND retention_until IS NULL
            AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL
            AND result_payload IS NULL AND result_sha256 IS NULL
            AND error_code IS NULL AND error_message IS NULL
            AND result_expires_at IS NULL AND result_purged_at IS NULL)
        OR
        (status = 'success'
            AND started_at IS NOT NULL AND completed_at IS NOT NULL AND retention_until >= completed_at + INTERVAL '180 days'
            AND lease_owner IS NULL AND lease_expires_at IS NULL
            AND error_code IS NULL AND error_message IS NULL
            AND result_expires_at >= completed_at + INTERVAL '24 hours'
            AND ((result_purged_at IS NULL AND result_payload IS NOT NULL AND result_sha256 IS NOT NULL)
                OR (result_purged_at >= result_expires_at AND result_payload IS NULL AND result_sha256 IS NULL)))
        OR
        (status = 'error'
            AND started_at IS NOT NULL AND completed_at IS NOT NULL AND retention_until >= completed_at + INTERVAL '180 days'
            AND lease_owner IS NULL AND lease_expires_at IS NULL
            AND result_payload IS NULL AND result_sha256 IS NULL
            AND error_code IS NOT NULL AND result_expires_at IS NULL AND result_purged_at IS NULL)
        OR
        (status = 'interrupted'
            AND completed_at IS NOT NULL AND retention_until >= completed_at + INTERVAL '180 days'
            AND lease_owner IS NULL AND lease_expires_at IS NULL
            AND result_payload IS NULL AND result_sha256 IS NULL
            AND error_code IS NOT NULL AND result_expires_at IS NULL AND result_purged_at IS NULL)
    )
);

CREATE OR REPLACE FUNCTION nutriathena_agent.touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_agent_threads_updated_at
    BEFORE UPDATE ON nutriathena_agent.agent_threads
    FOR EACH ROW EXECUTE FUNCTION nutriathena_agent.touch_updated_at();
CREATE TRIGGER trg_agent_runs_updated_at
    BEFORE UPDATE ON nutriathena_agent.agent_runs
    FOR EACH ROW EXECUTE FUNCTION nutriathena_agent.touch_updated_at();

CREATE INDEX idx_agent_runs_pending
    ON nutriathena_agent.agent_runs (created_at, run_id) WHERE status = 'pending';
CREATE INDEX idx_agent_runs_expired_lease
    ON nutriathena_agent.agent_runs (lease_expires_at, run_id) WHERE status = 'running';
CREATE INDEX idx_agent_runs_result_expiry
    ON nutriathena_agent.agent_runs (result_expires_at, run_id)
    WHERE status = 'success' AND result_purged_at IS NULL;
CREATE INDEX idx_agent_runs_retention
    ON nutriathena_agent.agent_runs (retention_until, run_id) WHERE retention_until IS NOT NULL;
CREATE INDEX idx_agent_threads_retention
    ON nutriathena_agent.agent_threads (created_at, thread_id);
