-- A submission is never repeated after its first HTTP attempt unless its outcome is known.
ALTER TABLE healthmind.ai_task_attempts
    ADD COLUMN agent_submission_state VARCHAR(16) NOT NULL DEFAULT 'new'
        CHECK (agent_submission_state IN ('new', 'submitting', 'uncertain', 'attached'));
