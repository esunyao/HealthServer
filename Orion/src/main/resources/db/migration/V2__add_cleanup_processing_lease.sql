ALTER TABLE "User".file_cleanup_tasks
    ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_file_cleanup_tasks_processing
    ON "User".file_cleanup_tasks (status, processing_started_at)
    WHERE status = 'processing';
