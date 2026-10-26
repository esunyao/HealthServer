ALTER TABLE nutri.meal_capture_sessions
    DROP CONSTRAINT meal_capture_sessions_status_check;
ALTER TABLE nutri.meal_capture_sessions
    ADD CONSTRAINT meal_capture_sessions_status_check
    CHECK (status IN ('created', 'uploading', 'ready_for_analysis', 'analysing', 'needs_review', 'completed', 'failed', 'expired', 'cancelled'));

ALTER TABLE nutri.meal_records
    DROP CONSTRAINT meal_records_analysis_status_check;
ALTER TABLE nutri.meal_records
    ADD CONSTRAINT meal_records_analysis_status_check
    CHECK (analysis_status IN ('queued', 'analysing', 'needs_review', 'completed', 'failed'));

CREATE TABLE nutri.meal_analysis_reports (
    meal_id BIGINT PRIMARY KEY REFERENCES nutri.meal_records(meal_id) ON DELETE CASCADE,
    task_id UUID NOT NULL,
    source_event_id UUID NOT NULL UNIQUE,
    event_occurred_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('completed', 'failed', 'needs_review')),
    overall_confidence NUMERIC(5,4) CHECK (overall_confidence IS NULL OR overall_confidence BETWEEN 0 AND 1),
    result_version INTEGER CHECK (result_version IS NULL OR result_version > 0),
    reason_code VARCHAR(64) CHECK (reason_code IS NULL OR reason_code ~ '^[A-Z0-9_]{1,64}$'),
    reason_message VARCHAR(500) CHECK (reason_message IS NULL OR BTRIM(reason_message) <> ''),
    analyzed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_meal_analysis_reports_reason CHECK (
        (status = 'completed' AND overall_confidence IS NOT NULL AND result_version IS NOT NULL AND reason_code IS NULL AND reason_message IS NULL)
        OR (status IN ('failed', 'needs_review') AND overall_confidence IS NULL AND result_version IS NULL AND reason_code IS NOT NULL)
    )
);

CREATE INDEX idx_meal_analysis_reports_status ON nutri.meal_analysis_reports(status, event_occurred_at DESC);

CREATE TABLE nutri.analysis_result_dead_letters (
    dead_letter_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id UUID,
    event_type VARCHAR(100),
    attempted_meal_id BIGINT,
    payload_sha256 CHAR(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    raw_payload TEXT NOT NULL,
    failure_code VARCHAR(64) NOT NULL CHECK (failure_code ~ '^[A-Z0-9_]{1,64}$'),
    failure_message VARCHAR(1000) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_analysis_result_dead_letters_event ON nutri.analysis_result_dead_letters(event_id, created_at DESC);
CREATE INDEX idx_analysis_result_dead_letters_created ON nutri.analysis_result_dead_letters(created_at DESC);
