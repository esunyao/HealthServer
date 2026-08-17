CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS nutri;

CREATE OR REPLACE FUNCTION nutri.set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE nutri.nutrient_definitions (
    nutrient_id BIGINT PRIMARY KEY CHECK (nutrient_id > 0),
    nutrient_code VARCHAR(64) NOT NULL UNIQUE,
    nutrient_name VARCHAR(100) NOT NULL,
    unit VARCHAR(16) NOT NULL,
    nutrient_category VARCHAR(32) NOT NULL CHECK (nutrient_category IN ('energy', 'macro', 'micro', 'other')),
    display_order INTEGER NOT NULL DEFAULT 0 CHECK (display_order >= 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE nutri.meal_capture_sessions (
    capture_session_id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    client_request_id UUID NOT NULL,
    source VARCHAR(24) NOT NULL DEFAULT 'personal_photo' CHECK (source IN ('personal_photo')),
    status VARCHAR(32) NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'uploading', 'ready_for_analysis', 'analysing', 'completed', 'failed', 'expired', 'cancelled')),
    timezone VARCHAR(64) NOT NULL,
    max_image_count SMALLINT NOT NULL DEFAULT 10 CHECK (max_image_count BETWEEN 1 AND 10),
    expires_at TIMESTAMPTZ NOT NULL,
    analysis_requested_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_capture_sessions_user_request UNIQUE (user_id, client_request_id)
);
CREATE INDEX idx_capture_sessions_user_status ON nutri.meal_capture_sessions(user_id, status, created_at DESC);
CREATE INDEX idx_capture_sessions_expiry ON nutri.meal_capture_sessions(expires_at) WHERE status IN ('created', 'uploading', 'ready_for_analysis', 'analysing');

CREATE TABLE nutri.meal_capture_images (
    image_id BIGINT PRIMARY KEY CHECK (image_id > 0),
    capture_session_id UUID NOT NULL REFERENCES nutri.meal_capture_sessions(capture_session_id) ON DELETE CASCADE,
    slot_no SMALLINT NOT NULL CHECK (slot_no BETWEEN 1 AND 10),
    bucket VARCHAR(255) NOT NULL,
    object_key VARCHAR(1024) NOT NULL UNIQUE,
    content_type VARCHAR(64) NOT NULL CHECK (content_type IN ('image/jpeg', 'image/png', 'image/webp')),
    content_length BIGINT NOT NULL CHECK (content_length BETWEEN 1 AND 10485760),
    captured_at TIMESTAMPTZ,
    status VARCHAR(16) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'deleted', 'expired')),
    confirmed_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_capture_images_session_slot UNIQUE (capture_session_id, slot_no),
    CONSTRAINT ck_capture_images_lifecycle CHECK (
        (status = 'pending' AND confirmed_at IS NULL AND deleted_at IS NULL)
        OR (status = 'confirmed' AND confirmed_at IS NOT NULL AND deleted_at IS NULL)
        OR (status IN ('deleted', 'expired') AND deleted_at IS NOT NULL)
    )
);
CREATE INDEX idx_capture_images_session_status ON nutri.meal_capture_images(capture_session_id, status);

CREATE TABLE nutri.integration_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL REFERENCES nutri.meal_capture_sessions(capture_session_id) ON DELETE CASCADE,
    aggregate_type VARCHAR(64) NOT NULL DEFAULT 'meal_capture_session',
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    status VARCHAR(16) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'published', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    last_error VARCHAR(1000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_outbox_capture_event UNIQUE (aggregate_id, event_type)
);
CREATE INDEX idx_outbox_delivery ON nutri.integration_outbox(status, next_attempt_at) WHERE status IN ('pending', 'failed');

CREATE TABLE nutri.integration_inbox (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    source_service VARCHAR(64) NOT NULL,
    payload_sha256 CHAR(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    status VARCHAR(16) NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'processed', 'failed')),
    processed_at TIMESTAMPTZ,
    last_error VARCHAR(1000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_inbox_status ON nutri.integration_inbox(status, created_at);

CREATE TABLE nutri.meal_records (
    meal_id BIGINT PRIMARY KEY CHECK (meal_id > 0),
    capture_session_id UUID NOT NULL UNIQUE REFERENCES nutri.meal_capture_sessions(capture_session_id),
    user_id UUID NOT NULL,
    meal_type VARCHAR(16) NOT NULL CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack', 'other')),
    consumed_at TIMESTAMPTZ NOT NULL,
    timezone VARCHAR(64) NOT NULL,
    local_date DATE NOT NULL,
    entry_source VARCHAR(24) NOT NULL DEFAULT 'ai_photo' CHECK (entry_source IN ('ai_photo')),
    notes VARCHAR(1000),
    status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deleted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT ck_meal_records_lifecycle CHECK (
        (status = 'active' AND deleted_at IS NULL)
        OR (status = 'deleted' AND deleted_at IS NOT NULL)
    )
);
CREATE INDEX idx_meal_records_user_local_type ON nutri.meal_records(user_id, local_date DESC, meal_type) WHERE status = 'active';
CREATE INDEX idx_meal_records_user_time ON nutri.meal_records(user_id, consumed_at DESC) WHERE status = 'active';
CREATE INDEX idx_meal_records_notes_trgm ON nutri.meal_records USING GIN (notes gin_trgm_ops) WHERE status = 'active' AND notes IS NOT NULL;

CREATE TABLE nutri.meal_items (
    item_id BIGINT PRIMARY KEY CHECK (item_id > 0),
    meal_id BIGINT NOT NULL REFERENCES nutri.meal_records(meal_id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    display_name VARCHAR(150) NOT NULL CHECK (BTRIM(display_name) <> ''),
    estimated_weight_g NUMERIC(12,3) CHECK (estimated_weight_g > 0),
    confidence NUMERIC(5,4) CHECK (confidence BETWEEN 0 AND 1),
    data_source VARCHAR(16) NOT NULL DEFAULT 'ai' CHECK (data_source IN ('ai', 'manual')),
    user_corrected BOOLEAN NOT NULL DEFAULT FALSE,
    notes VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_meal_items_sequence UNIQUE (meal_id, sequence_no)
);
CREATE INDEX idx_meal_items_meal ON nutri.meal_items(meal_id);
CREATE INDEX idx_meal_items_name_trgm ON nutri.meal_items USING GIN (display_name gin_trgm_ops);

CREATE TABLE nutri.meal_item_nutrient_values (
    item_id BIGINT NOT NULL REFERENCES nutri.meal_items(item_id) ON DELETE CASCADE,
    nutrient_id BIGINT NOT NULL REFERENCES nutri.nutrient_definitions(nutrient_id),
    nutrient_code_snapshot VARCHAR(64) NOT NULL,
    nutrient_name_snapshot VARCHAR(100) NOT NULL,
    unit_snapshot VARCHAR(16) NOT NULL,
    amount NUMERIC(18,6) NOT NULL CHECK (amount >= 0),
    data_source VARCHAR(16) NOT NULL DEFAULT 'ai' CHECK (data_source IN ('ai', 'manual')),
    user_corrected BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (item_id, nutrient_id)
);
CREATE INDEX idx_meal_item_nutrients_code ON nutri.meal_item_nutrient_values(nutrient_code_snapshot);

CREATE TABLE nutri.meal_nutrition_values (
    meal_id BIGINT NOT NULL REFERENCES nutri.meal_records(meal_id) ON DELETE CASCADE,
    nutrient_id BIGINT NOT NULL REFERENCES nutri.nutrient_definitions(nutrient_id),
    nutrient_code_snapshot VARCHAR(64) NOT NULL,
    nutrient_name_snapshot VARCHAR(100) NOT NULL,
    unit_snapshot VARCHAR(16) NOT NULL,
    total_amount NUMERIC(18,6) NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (meal_id, nutrient_id)
);

CREATE TABLE nutri.daily_nutrition_summaries (
    summary_id BIGINT PRIMARY KEY CHECK (summary_id > 0),
    user_id UUID NOT NULL,
    local_date DATE NOT NULL,
    meal_count INTEGER NOT NULL DEFAULT 0 CHECK (meal_count >= 0),
    last_recalculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_daily_summary_user_date UNIQUE (user_id, local_date)
);

CREATE TABLE nutri.daily_nutrition_values (
    summary_id BIGINT NOT NULL REFERENCES nutri.daily_nutrition_summaries(summary_id) ON DELETE CASCADE,
    nutrient_id BIGINT NOT NULL REFERENCES nutri.nutrient_definitions(nutrient_id),
    nutrient_code_snapshot VARCHAR(64) NOT NULL,
    nutrient_name_snapshot VARCHAR(100) NOT NULL,
    unit_snapshot VARCHAR(16) NOT NULL,
    total_amount NUMERIC(18,6) NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (summary_id, nutrient_id)
);

CREATE TRIGGER trg_nutrient_definitions_updated BEFORE UPDATE ON nutri.nutrient_definitions FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();
CREATE TRIGGER trg_capture_sessions_updated BEFORE UPDATE ON nutri.meal_capture_sessions FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();
CREATE TRIGGER trg_outbox_updated BEFORE UPDATE ON nutri.integration_outbox FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();
CREATE TRIGGER trg_inbox_updated BEFORE UPDATE ON nutri.integration_inbox FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();
CREATE TRIGGER trg_meal_records_updated BEFORE UPDATE ON nutri.meal_records FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();
CREATE TRIGGER trg_meal_items_updated BEFORE UPDATE ON nutri.meal_items FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();
CREATE TRIGGER trg_meal_item_nutrients_updated BEFORE UPDATE ON nutri.meal_item_nutrient_values FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();
CREATE TRIGGER trg_meal_nutrition_updated BEFORE UPDATE ON nutri.meal_nutrition_values FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();
CREATE TRIGGER trg_daily_summaries_updated BEFORE UPDATE ON nutri.daily_nutrition_summaries FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();
CREATE TRIGGER trg_daily_nutrition_updated BEFORE UPDATE ON nutri.daily_nutrition_values FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();

INSERT INTO nutri.nutrient_definitions(nutrient_id, nutrient_code, nutrient_name, unit, nutrient_category, display_order) VALUES
    (1001, 'ENERGY_KCAL', '能量', 'kcal', 'energy', 1),
    (1002, 'PROTEIN', '蛋白质', 'g', 'macro', 2),
    (1003, 'FAT', '脂肪', 'g', 'macro', 3),
    (1004, 'CARBOHYDRATE', '碳水化合物', 'g', 'macro', 4),
    (1005, 'SUGAR', '糖', 'g', 'macro', 5),
    (1006, 'DIETARY_FIBER', '膳食纤维', 'g', 'macro', 6),
    (1007, 'SODIUM', '钠', 'mg', 'micro', 7),
    (1008, 'CALCIUM', '钙', 'mg', 'micro', 8),
    (1009, 'IRON', '铁', 'mg', 'micro', 9),
    (1010, 'POTASSIUM', '钾', 'mg', 'micro', 10),
    (1011, 'VITAMIN_C', '维生素C', 'mg', 'micro', 11);
