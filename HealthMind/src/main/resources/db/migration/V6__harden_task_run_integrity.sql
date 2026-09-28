-- Stop HealthMind before applying this migration. It adds integrity checks and never clears runtime data.
DO $$
DECLARE
    conflicting_ids TEXT;
BEGIN
    SELECT string_agg(task_id::text, ', ' ORDER BY task_id::text)
      INTO conflicting_ids
      FROM (
          SELECT task_id
            FROM healthmind.ai_task_attempts
           WHERE status IN ('pending', 'running')
           GROUP BY task_id
          HAVING COUNT(*) > 1
           ORDER BY task_id
           LIMIT 20
      ) conflicts;
    IF conflicting_ids IS NOT NULL THEN
        RAISE EXCEPTION 'V6 found tasks with multiple active attempts; resolve task_id values before retrying: %', conflicting_ids;
    END IF;

    SELECT string_agg(task_id::text, ', ' ORDER BY task_id::text)
      INTO conflicting_ids
      FROM (
          SELECT t.task_id
            FROM healthmind.ai_tasks t
            JOIN healthmind.workflow_releases wr ON wr.release_id = t.workflow_release_id
           WHERE t.task_type_id <> wr.task_type_id
           ORDER BY t.task_id
           LIMIT 20
      ) conflicts;
    IF conflicting_ids IS NOT NULL THEN
        RAISE EXCEPTION 'V6 found tasks whose task type differs from the pinned release; resolve task_id values before retrying: %', conflicting_ids;
    END IF;

    SELECT string_agg(task_id::text, ', ' ORDER BY task_id::text)
      INTO conflicting_ids
      FROM (
          SELECT task_id
            FROM healthmind.ai_task_attempts
           WHERE status = 'succeeded'
           GROUP BY task_id
          HAVING COUNT(*) > 1
           ORDER BY task_id
           LIMIT 20
      ) conflicts;
    IF conflicting_ids IS NOT NULL THEN
        RAISE EXCEPTION 'V6 found tasks with multiple succeeded attempts; resolve task_id values before retrying: %', conflicting_ids;
    END IF;

    SELECT string_agg(attempt_id::text, ', ' ORDER BY attempt_id::text)
      INTO conflicting_ids
      FROM (
          SELECT attempt_id
            FROM healthmind.ai_task_attempts
           WHERE status = 'succeeded' AND agent_managed AND agent_run_id IS NULL
           ORDER BY attempt_id
           LIMIT 20
      ) conflicts;
    IF conflicting_ids IS NOT NULL THEN
        RAISE EXCEPTION 'V6 found succeeded Agent attempts without a run ID; resolve attempt_id values before retrying: %', conflicting_ids;
    END IF;

    SELECT string_agg(rt.release_id::text || '/' || rt.tool_id::text, ', ' ORDER BY rt.release_id::text, rt.tool_id::text)
      INTO conflicting_ids
      FROM healthmind.workflow_release_tools rt
      LEFT JOIN healthmind.ai_tool_definitions d ON d.tool_id = rt.tool_id
     WHERE d.tool_id IS NULL;
    IF conflicting_ids IS NOT NULL THEN
        RAISE EXCEPTION 'V6 found release tool bindings without a source definition; resolve release_id/tool_id values before retrying: %', conflicting_ids;
    END IF;

    SELECT string_agg(r.task_id::text, ', ' ORDER BY r.task_id::text)
      INTO conflicting_ids
      FROM healthmind.ai_task_results r
     WHERE NOT EXISTS (
           SELECT 1
             FROM healthmind.ai_task_attempts a
            WHERE a.task_id = r.task_id
              AND a.status = 'succeeded'
              AND a.agent_run_id IS NOT NULL
     );
    IF conflicting_ids IS NOT NULL THEN
        RAISE EXCEPTION 'V6 found results without a succeeded Agent run; resolve task_id values before retrying: %', conflicting_ids;
    END IF;

    SELECT string_agg(artifact.artifact_id::text, ', ' ORDER BY artifact.artifact_id::text)
      INTO conflicting_ids
      FROM healthmind.ai_task_artifacts artifact
      JOIN healthmind.ai_task_attempts a ON a.attempt_id = artifact.attempt_id
     WHERE artifact.attempt_id IS NOT NULL
       AND artifact.task_id <> a.task_id;
    IF conflicting_ids IS NOT NULL THEN
        RAISE EXCEPTION 'V6 found artifacts linked to another task attempt; resolve artifact_id values before retrying: %', conflicting_ids;
    END IF;

    SELECT string_agg(i.invocation_id::text, ', ' ORDER BY i.invocation_id::text)
      INTO conflicting_ids
      FROM healthmind.ai_tool_invocations i
      JOIN healthmind.ai_tasks t ON t.task_id = i.task_id
      JOIN healthmind.ai_task_attempts a ON a.attempt_id = i.attempt_id
      LEFT JOIN healthmind.workflow_release_tools rt
        ON rt.release_id = i.release_id AND rt.tool_id = i.tool_id
     WHERE a.task_id <> i.task_id
        OR t.workflow_release_id <> i.release_id
        OR a.task_id <> t.task_id
        OR a.agent_managed IS NOT TRUE
        OR rt.release_id IS NULL;
    IF conflicting_ids IS NOT NULL THEN
        RAISE EXCEPTION 'V6 found tool invocations outside their task, attempt, or release binding; resolve invocation_id values before retrying: %', conflicting_ids;
    END IF;

    SELECT string_agg(wr.release_id::text, ', ' ORDER BY wr.release_id::text)
      INTO conflicting_ids
      FROM healthmind.workflow_releases wr
      JOIN healthmind.workflow_release_tools rt ON rt.release_id = wr.release_id
      JOIN healthmind.ai_tool_definitions d ON d.tool_id = rt.tool_id
     WHERE wr.status = 'production'
       AND d.updated_at > wr.created_at;
    IF conflicting_ids IS NOT NULL THEN
        RAISE EXCEPTION 'V6 found production releases whose tool definitions changed after release creation; inspect and reconcile these release_id values before retrying: %', conflicting_ids;
    END IF;
END;
$$;

ALTER TABLE healthmind.workflow_releases
    ADD CONSTRAINT uk_workflow_releases_task_release UNIQUE (task_type_id, release_id);

CREATE OR REPLACE FUNCTION healthmind.protect_agent_release_identity() RETURNS TRIGGER AS $$
BEGIN
    IF (OLD.task_type_id, OLD.release_version, OLD.agent_deployment_key, OLD.agent_assistant_id,
        OLD.agent_artifact_sha256, OLD.input_schema_version, OLD.input_schema, OLD.input_schema_sha256,
        OLD.output_schema_version, OLD.output_schema, OLD.output_schema_sha256, OLD.timeout_seconds, OLD.max_attempts)
        IS DISTINCT FROM
       (NEW.task_type_id, NEW.release_version, NEW.agent_deployment_key, NEW.agent_assistant_id,
        NEW.agent_artifact_sha256, NEW.input_schema_version, NEW.input_schema, NEW.input_schema_sha256,
        NEW.output_schema_version, NEW.output_schema, NEW.output_schema_sha256, NEW.timeout_seconds, NEW.max_attempts) THEN
        RAISE EXCEPTION 'Agent release identity and contracts are immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

ALTER TABLE healthmind.ai_tasks
    ADD CONSTRAINT uk_ai_tasks_task_release UNIQUE (task_id, workflow_release_id),
    DROP CONSTRAINT ai_tasks_workflow_release_id_fkey,
    ADD CONSTRAINT fk_ai_tasks_task_type_release
        FOREIGN KEY (task_type_id, workflow_release_id)
        REFERENCES healthmind.workflow_releases(task_type_id, release_id);

ALTER TABLE healthmind.workflow_release_tools
    ADD COLUMN request_schema_version VARCHAR(32),
    ADD COLUMN request_schema JSONB,
    ADD COLUMN request_schema_sha256 CHAR(64),
    ADD COLUMN response_schema_version VARCHAR(32),
    ADD COLUMN response_schema JSONB,
    ADD COLUMN response_schema_sha256 CHAR(64);

ALTER TABLE healthmind.workflow_release_tools DISABLE TRIGGER trg_protect_promoted_agent_tools;
UPDATE healthmind.workflow_release_tools rt
   SET request_schema_version = d.request_schema_version,
       request_schema = d.request_schema,
       request_schema_sha256 = d.request_schema_sha256,
       response_schema_version = d.response_schema_version,
       response_schema = d.response_schema,
       response_schema_sha256 = d.response_schema_sha256
  FROM healthmind.ai_tool_definitions d
 WHERE d.tool_id = rt.tool_id;
ALTER TABLE healthmind.workflow_release_tools ENABLE TRIGGER trg_protect_promoted_agent_tools;

ALTER TABLE healthmind.workflow_release_tools
    ALTER COLUMN request_schema_version SET NOT NULL,
    ALTER COLUMN request_schema SET NOT NULL,
    ALTER COLUMN request_schema_sha256 SET NOT NULL,
    ALTER COLUMN response_schema_version SET NOT NULL,
    ALTER COLUMN response_schema SET NOT NULL,
    ALTER COLUMN response_schema_sha256 SET NOT NULL,
    ADD CONSTRAINT ck_workflow_release_tools_request_schema
        CHECK (jsonb_typeof(request_schema) = 'object' AND request_schema_sha256 ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT ck_workflow_release_tools_response_schema
        CHECK (jsonb_typeof(response_schema) = 'object' AND response_schema_sha256 ~ '^[0-9a-f]{64}$');

ALTER TABLE healthmind.ai_task_attempts
    ADD COLUMN workflow_release_id UUID,
    ADD COLUMN lease_owner VARCHAR(128),
    ADD COLUMN lease_expires_at TIMESTAMPTZ,
    ADD COLUMN lease_version BIGINT NOT NULL DEFAULT 0 CHECK (lease_version >= 0);

UPDATE healthmind.ai_task_attempts a
   SET workflow_release_id = t.workflow_release_id
  FROM healthmind.ai_tasks t
 WHERE t.task_id = a.task_id;

UPDATE healthmind.ai_task_attempts
   SET lease_owner = 'v5-migration', lease_expires_at = NOW(),
       agent_submission_state = CASE
           WHEN agent_managed AND agent_submission_state = 'new' THEN 'uncertain'
           ELSE agent_submission_state
       END
 WHERE status = 'running';

ALTER TABLE healthmind.ai_task_attempts
    ALTER COLUMN workflow_release_id SET NOT NULL,
    DROP CONSTRAINT ai_task_attempts_task_id_fkey,
    ADD CONSTRAINT fk_ai_task_attempts_task_release
        FOREIGN KEY (task_id, workflow_release_id)
        REFERENCES healthmind.ai_tasks(task_id, workflow_release_id) ON DELETE RESTRICT,
    ADD CONSTRAINT uk_ai_task_attempts_task_attempt UNIQUE (task_id, attempt_id),
    ADD CONSTRAINT uk_ai_task_attempts_task_attempt_release UNIQUE (task_id, attempt_id, workflow_release_id),
    ADD CONSTRAINT uk_ai_task_attempts_result_provenance
        UNIQUE (task_id, attempt_id, workflow_release_id, agent_run_id),
    ADD CONSTRAINT ck_ai_task_attempts_lease_pair
        CHECK ((lease_owner IS NULL) = (lease_expires_at IS NULL));

CREATE UNIQUE INDEX uk_ai_task_attempts_active_task
    ON healthmind.ai_task_attempts(task_id)
    WHERE status IN ('pending', 'running');
CREATE INDEX idx_ai_task_attempts_lease_poll
    ON healthmind.ai_task_attempts(status, agent_next_check_at, lease_expires_at)
    WHERE status = 'running' AND agent_managed;

ALTER TABLE healthmind.ai_task_results
    ADD COLUMN attempt_id UUID,
    ADD COLUMN workflow_release_id UUID,
    ADD COLUMN agent_run_id UUID;

UPDATE healthmind.ai_task_results r
   SET attempt_id = a.attempt_id,
       workflow_release_id = a.workflow_release_id,
       agent_run_id = a.agent_run_id
  FROM healthmind.ai_task_attempts a
 WHERE a.task_id = r.task_id
   AND a.status = 'succeeded'
   AND a.agent_run_id IS NOT NULL;

ALTER TABLE healthmind.ai_task_results
    ALTER COLUMN attempt_id SET NOT NULL,
    ALTER COLUMN workflow_release_id SET NOT NULL,
    ALTER COLUMN agent_run_id SET NOT NULL,
    DROP CONSTRAINT ai_task_results_task_id_fkey,
    ADD CONSTRAINT fk_ai_task_results_task_release
        FOREIGN KEY (task_id, workflow_release_id)
        REFERENCES healthmind.ai_tasks(task_id, workflow_release_id),
    ADD CONSTRAINT fk_ai_task_results_attempt_provenance
        FOREIGN KEY (task_id, attempt_id, workflow_release_id, agent_run_id)
        REFERENCES healthmind.ai_task_attempts(task_id, attempt_id, workflow_release_id, agent_run_id);

CREATE FUNCTION healthmind.require_succeeded_result_attempt() RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM healthmind.ai_task_attempts a
         WHERE a.task_id = NEW.task_id
           AND a.attempt_id = NEW.attempt_id
           AND a.workflow_release_id = NEW.workflow_release_id
           AND a.agent_run_id = NEW.agent_run_id
           AND a.status = 'succeeded'
    ) THEN
        RAISE EXCEPTION 'Task result must reference a succeeded Agent attempt';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_ai_task_results_succeeded_attempt
    BEFORE INSERT OR UPDATE ON healthmind.ai_task_results
    FOR EACH ROW EXECUTE FUNCTION healthmind.require_succeeded_result_attempt();

ALTER TABLE healthmind.ai_task_artifacts
    DROP CONSTRAINT ai_task_artifacts_task_id_fkey,
    DROP CONSTRAINT ai_task_artifacts_attempt_id_fkey,
    ADD CONSTRAINT fk_ai_task_artifacts_task
        FOREIGN KEY (task_id) REFERENCES healthmind.ai_tasks(task_id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_ai_task_artifacts_attempt
        FOREIGN KEY (task_id, attempt_id) REFERENCES healthmind.ai_task_attempts(task_id, attempt_id) ON DELETE RESTRICT;

ALTER TABLE healthmind.ai_tool_invocations
    DROP CONSTRAINT ai_tool_invocations_task_id_fkey,
    DROP CONSTRAINT ai_tool_invocations_attempt_id_fkey,
    DROP CONSTRAINT ai_tool_invocations_release_id_fkey,
    DROP CONSTRAINT ai_tool_invocations_tool_id_fkey,
    DROP CONSTRAINT uk_ai_tool_invocations_idempotency,
    ADD CONSTRAINT uk_ai_tool_invocations_idempotency UNIQUE (attempt_id, tool_id, idempotency_key),
    ADD CONSTRAINT fk_ai_tool_invocations_attempt_release
        FOREIGN KEY (task_id, attempt_id, release_id)
        REFERENCES healthmind.ai_task_attempts(task_id, attempt_id, workflow_release_id),
    ADD CONSTRAINT fk_ai_tool_invocations_release_tool
        FOREIGN KEY (release_id, tool_id)
        REFERENCES healthmind.workflow_release_tools(release_id, tool_id),
    ADD COLUMN replay_count INTEGER NOT NULL DEFAULT 0 CHECK (replay_count >= 0),
    ADD COLUMN last_replayed_at TIMESTAMPTZ;

ALTER TABLE healthmind.integration_outbox
    ADD COLUMN claim_version BIGINT NOT NULL DEFAULT 0 CHECK (claim_version >= 0),
    DROP CONSTRAINT integration_outbox_task_id_fkey,
    ADD CONSTRAINT fk_integration_outbox_task
        FOREIGN KEY (task_id) REFERENCES healthmind.ai_tasks(task_id) ON DELETE RESTRICT;

CREATE FUNCTION healthmind.protect_integration_outbox_retention() RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status <> 'published' OR OLD.retention_until > NOW() THEN
        RAISE EXCEPTION 'Outbox rows may be deleted only after publication and retention';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_protect_integration_outbox_retention
    BEFORE DELETE ON healthmind.integration_outbox
    FOR EACH ROW EXECUTE FUNCTION healthmind.protect_integration_outbox_retention();
