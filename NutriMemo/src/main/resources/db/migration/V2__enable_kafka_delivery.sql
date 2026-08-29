ALTER TABLE nutri.integration_outbox DROP CONSTRAINT integration_outbox_status_check;
ALTER TABLE nutri.integration_outbox
    ADD CONSTRAINT integration_outbox_status_check CHECK (status IN ('pending', 'publishing', 'published', 'failed'));
ALTER TABLE nutri.integration_outbox ADD COLUMN locked_at TIMESTAMPTZ;

ALTER TABLE nutri.integration_inbox ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 1 CHECK (attempt_count >= 1);

CREATE INDEX idx_outbox_stale_publishing ON nutri.integration_outbox(locked_at) WHERE status = 'publishing';
