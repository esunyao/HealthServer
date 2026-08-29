-- Execute with psql variables: release_id, actor_id, reason, trace_id.
BEGIN;
SELECT pg_advisory_xact_lock(hashtextextended('healthmind.workflow.production', 0));

WITH target AS (
    SELECT task_type_id
    FROM healthmind.workflow_releases
    WHERE release_id = :'release_id'::uuid AND status = 'candidate'
    FOR UPDATE
), retired AS (
    UPDATE healthmind.workflow_releases wr
       SET status = 'retired', retired_by = :'actor_id'::uuid, retired_at = NOW()
      FROM target
     WHERE wr.task_type_id = target.task_type_id AND wr.status = 'production'
    RETURNING wr.release_id
)
INSERT INTO healthmind.workflow_release_audits
    (audit_id, release_id, action, from_status, to_status, actor_id, reason, trace_id)
SELECT gen_random_uuid(), release_id, 'retired', 'production', 'retired', :'actor_id'::uuid, :'reason', :'trace_id'
FROM retired;

UPDATE healthmind.workflow_releases
   SET status = 'production', promoted_by = :'actor_id'::uuid, promoted_at = NOW()
 WHERE release_id = :'release_id'::uuid AND status = 'candidate';

INSERT INTO healthmind.workflow_release_audits
    (audit_id, release_id, action, from_status, to_status, actor_id, reason, trace_id)
VALUES
    (gen_random_uuid(), :'release_id'::uuid, 'promoted', 'candidate', 'production', :'actor_id'::uuid, :'reason', :'trace_id');
COMMIT;
